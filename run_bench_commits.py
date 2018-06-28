import os
import shutil
import subprocess

import click
import elasticsearch
import perf

try:
    from urllib.request import Request, urlopen
    from urllib.parse import urlparse
except ImportError:
    from urllib2 import Request, urlopen
    from urllib.parse import urlparse

BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', ))


def get_commit_list(start_commit, end_commit, worktree):
    commit_range = '%s..%s' % (start_commit, end_commit)
    commits = subprocess.check_output(['git', 'log', "--pretty=%h", commit_range], cwd=worktree).decode('utf8')
    commits = commits.split('\n')[:-1]
    commits.reverse()
    return commits


def run_benchmark(commit_hash, worktree):
    # clean up from former runs
    if commit_hash:
        subprocess.check_output(['git', 'checkout', 'elasticapm/base.py'], cwd=worktree)
        subprocess.check_output(['git', 'checkout', commit_hash], cwd=worktree)
        # set the timer thread to daemon, this fixes an issue with the timer thread
        # not exiting in old commits
        subprocess.check_output(
            "sed -i '' -e 's/self\._send_timer\.start/self\._send_timer\.daemon=True; self\._send_timer\.start/g' elasticapm/base.py",
            shell=True,
            cwd=worktree,
        )
    env = dict(**os.environ)
    env['PYTHONPATH'] = worktree
    env['COMMIT_TIMESTAMP'], env['COMMIT_SHA'], env['COMMIT_MESSAGE'] = subprocess.check_output(
        ['git', 'log', '-1' ,'--pretty=%aI\t%H\t%B'],
        cwd=worktree,
    ).decode('utf8').split('\t', 2)
    output_files = []
    for bench_type, flag in (('time', None), ('tracemalloc', '--tracemalloc')):
        output_file = 'result.%s.%s.json' % (bench_type, commit_hash)
        test_cmd = ['python', 'run_bench.py', '-o', output_file, '--inherit-environ', 'COMMIT_TIMESTAMP,COMMIT_SHA,COMMIT_MESSAGE,COMMIT_MESSAGE,PYTHONPATH']
        if flag:
            test_cmd.append(flag)
        print(subprocess.check_output(
            test_cmd,
            stderr=subprocess.STDOUT,
            env=env,
        ))
        output_files.append(output_file)
    if commit_hash:
        subprocess.check_output(['git', 'checkout', 'elasticapm/base.py'], cwd=worktree)
    return output_files


def upload_benchmark(es_url, es_user, es_password, files):
    if '@' not in es_url and es_user:
        parts = urlparse(es_url)
        es_url = '%s://%s:%s@%s%s' % (
            parts.scheme,
            es_user,
            es_password,
            parts.netloc,
            parts.path,
        )
    es = elasticsearch.Elasticsearch([es_url])
    result = []
    for file in files:
        suite = perf.BenchmarkSuite.load(file)
        for bench in suite:
            ncalibration_runs = sum(run._is_calibration() for run in bench._runs)
            nrun = bench.get_nrun()
            loops = bench.get_loops()
            inner_loops = bench.get_inner_loops()
            total_loops = loops * inner_loops
            meta = bench.get_metadata()
            meta['start_date'] = bench.get_dates()[0].isoformat(' ')
            output = {
                '_index': 'benchmark-agent-python-' + meta['timestamp'].split('T')[0],
                '@timestamp': meta.pop('timestamp'),
                'benchmark': meta.pop('name'),
                'meta': meta,
                'runs': {
                    'calibration': ncalibration_runs,
                    'with_values': nrun - ncalibration_runs,
                    'total': nrun,
                },
                'warmups_per_run': bench._get_nwarmup(),
                'values_per_run': bench._get_nvalue_per_run(),
                'median': bench.median(),
                'median_abs_dev': bench.median_abs_dev(),
                'mean': bench.mean(),
                'mean_std_dev': bench.stdev(),
                'primaryMetric': {
                    'score': bench.mean(),
                    'stdev': bench.stdev(),
                    'scorePercentiles': {},
                },
            }
            for p in (0, 5, 25, 50, 75, 95, 100):
                output['primaryMetric']['scorePercentiles']['%.1f' % p] = bench.percentile(p)
            result.append(output)
    for b in result:
        es.index(doc_type='doc', body=b, index=b.pop('_index'))


@click.command()
@click.option('--worktree', required=True, type=click.Path(),
              help='worktree of elastic-apm to run benchmarks in')
@click.option('--start-commit', default=None, help='first commit to benchmark. If left empty, current worktree state will be benchmarked')
@click.option('--end-commit', default=None, help='last commit to benchmark. If left empty, only start-commit will be benchmarked')
@click.option('--clone-url', default=None, help='Git URL to clone')
@click.option('--es-url', default=None, help='Elasticsearch URL')
@click.option('--es-user', default=None, help='Elasticsearch User')
@click.option('--es-password', default=None, help='Elasticsearch Password', envvar='ES_PASSWORD')
def run(worktree, start_commit, end_commit, clone_url, es_url, es_user, es_password):
    cloned = False
    if clone_url:
        if os.path.exists(worktree):
            raise click.UsageError("%s exists, can't clone" % worktree)
        subprocess.check_output(['git', 'clone', clone_url, worktree])
        cloned = True
    if start_commit:
        if end_commit:
            commits = get_commit_list(start_commit, end_commit, worktree)
        else:
            commits = [start_commit]
    else:
        commits = [None]
    json_files = []
    for commit in commits:
        json_files.extend(run_benchmark(commit, worktree))
    if cloned:
        shutil.rmtree(worktree)
    if es_url:
        upload_benchmark(es_url, es_user, es_password, json_files)


if __name__ == '__main__':
    run()
