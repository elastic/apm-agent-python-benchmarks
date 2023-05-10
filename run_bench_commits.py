import logging
import os
import random
import shutil
import subprocess
from urllib.parse import urlparse

import click
import elasticsearch
import pyperf

LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

logger = logging.getLogger(__name__)

BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def get_commit_list(start_commit, end_commit, worktree):
    if start_commit and end_commit:
        commit_range = "%s..%s" % (start_commit, end_commit)
        commits = subprocess.check_output(
            ["git", "log", "--pretty=%h", commit_range], cwd=worktree
        ).decode("utf8")
    elif start_commit:
        commits = subprocess.check_output(
            ["git", "log", "-1", start_commit, "--pretty=%h"], cwd=worktree
        ).decode("utf8")
    else:
        commits = subprocess.check_output(
            ["git", "log", "-1", "--pretty=%h"], cwd=worktree
        ).decode("utf8")
    commit_hashes = commits.split("\n")[:-1]
    commits = []
    for hash in commit_hashes:
        timestamp, sha, author, subject, commit_message = (
            subprocess.check_output(
                ["git", "log", hash, "-1", "--pretty=%aI\t%H\t%aE\t%s\t%b"],
                cwd=worktree,
            )
            .decode("utf8")
            .split("\t", 4)
        )
        commits.append(
            {
                "sha": sha,
                "@timestamp": timestamp,
                "title": subject,
                "message": commit_message,
                "author": author,
            }
        )
    commits.reverse()
    return commits


OVERWRITE_ALL = False  # ugly way to store overall-overwrite-status


def run_benchmark(commit_info, worktree, timing, tracemalloc, pattern, as_is):
    if not as_is:
        subprocess.check_output(
            ["git", "checkout", commit_info["sha"]],
            cwd=worktree,
            stderr=subprocess.STDOUT,
        )
    env = dict(**os.environ)
    env["PYTHONPATH"] = worktree
    env["COMMIT_TIMESTAMP"] = commit_info["@timestamp"]
    env["COMMIT_SHA"] = commit_info["sha"]
    env["COMMIT_MESSAGE"] = commit_info["title"]
    if pattern:
        env["BENCH_PATTERN"] = pattern
    output_files = []
    benches = []
    if timing:
        benches.append(("time", None))
    if tracemalloc:
        benches.append(("tracemalloc", "--tracemalloc"))
    overwrite_all_files = False
    for bench_type, flag in benches:
        output_file = "result.%s.%s.json" % (bench_type, commit_info["sha"])
        if os.path.exists(output_file):
            if overwrite_all_files:
                os.unlink(output_file)
            else:
                overwrite = click.prompt(
                    "{} exists. Overwrite? (y/n/all)".format(output_file), default="y"
                ).lower()
                if overwrite in ("", "y", "all"):
                    os.unlink(output_file)
                    if overwrite == "all":
                        global OVERWRITE_ALL
                        OVERWRITE_ALL = True
                else:
                    print(
                        "Skipped {} bench for {}".format(
                            bench_type, commit_info["sha"][:8]
                        )
                    )
                    continue
        test_cmd = [
            "python",
            "run_bench.py",
            "-o",
            output_file,
            "--inherit-environ",
            "COMMIT_TIMESTAMP,COMMIT_SHA,COMMIT_MESSAGE,PYTHONPATH,BENCH_PATTERN",
        ]
        if flag:
            test_cmd.append(flag)
        print(

            subprocess.check_output(
                test_cmd, stderr=subprocess.STDOUT, env=env
            ).decode()
        )
        output_files.append(output_file)
    return output_files


def upload_benchmark(es_url, es_user, es_password, files, commit_info, tags):
    if "@" not in es_url and es_user:
        parts = urlparse(es_url)
        es_url = "%s://%s:%s@%s%s" % (
            parts.scheme,
            es_user,
            es_password,
            parts.netloc,
            parts.path,
        )
    es = elasticsearch.Elasticsearch([es_url])
    result = []
    for file in files:
        suite = pyperf.BenchmarkSuite.load(file)
        for bench in suite:
            ncalibration_runs = sum(run._is_calibration() for run in bench._runs)
            nrun = bench.get_nrun()
            meta = bench.get_metadata()
            meta["start_date"] = bench.get_dates()[0].isoformat(" ")
            if meta["unit"] == "second":
                meta["unit"] = "milliseconds"
                result_factor = 1000
            else:
                result_factor = 1
            if tags:
                meta["tags"] = tags
            full_name = meta.pop("name")
            class_name = full_name.rsplit(".", 1)[0]
            short_name = class_name.rsplit(".", 1)[1]
            output = {
                "_index": "benchmark-python",
                "@timestamp": meta.pop("timestamp"),
                "benchmark_class": class_name,
                "benchmark_short_name": short_name,
                "benchmark": full_name,
                "meta": meta,
                "runs": {
                    "calibration": ncalibration_runs,
                    "with_values": nrun - ncalibration_runs,
                    "total": nrun,
                },
                "warmups_per_run": bench._get_nwarmup(),
                "values_per_run": bench._get_nvalue_per_run(),
                "median": bench.median() * result_factor,
                "median_abs_dev": bench.median_abs_dev() * result_factor,
                "mean": bench.mean() * result_factor,
                "mean_std_dev": bench.stdev() * result_factor,
                "percentiles": {},
            }
            for p in (0, 5, 25, 50, 75, 95, 99, 100):
                output["percentiles"]["%.1f" % p] = bench.percentile(p) * result_factor
            result.append(output)
    for b in result:
        es.index(body=b, index=b.pop("_index"))
    es.update(
        index="benchmark-py-commits",
        id=commit_info["sha"],
        body={
            "doc": {
                "@timestamp": commit_info["@timestamp"],
                "shortref": commit_info["sha"][:8],
                "title": commit_info["title"],
                "body": commit_info["message"],
                "author": commit_info["author"],
            },
            "doc_as_upsert": True,
        },
    )


@click.command()
@click.option(
    "--worktree",
    required=True,
    type=click.Path(),
    help="worktree of elastic-apm to run benchmarks in",
)
@click.option(
    "--start-commit",
    default=None,
    help="first commit to benchmark. If left empty, current worktree state will be benchmarked",
)
@click.option(
    "--end-commit",
    default=None,
    help="last commit to benchmark. If left empty, only start-commit will be benchmarked",
)
@click.option("--clone-url", default=None, help="Git URL to clone")
@click.option("--es-url", default=None, help="Elasticsearch URL")
@click.option("--es-user", default=None, help="Elasticsearch User")
@click.option(
    "--es-password", default=None, help="Elasticsearch Password", envvar="ES_PASSWORD"
)
@click.option(
    "--delete-output-files/--no-delete-output-files",
    default=False,
    help="Delete benchmark files",
)
@click.option(
    "--delete-repo/--no-delete-repo", default=False, help="Delete repo after run"
)
@click.option(
    "--randomize/--no-randomize", default=True, help="Randomize order of commits"
)
@click.option("--timing/--no-timing", default=True, help="Run timing benchmarks")
@click.option(
    "--tracemalloc/--no-tracemalloc", default=True, help="Run tracemalloc benchmarks"
)
@click.option(
    "--bench-pattern",
    default=None,
    help="An optional glob pattern to filter benchmarks by",
)
@click.option(
    "--as-is",
    default=False,
    is_flag=True,
    help="Run benchmark in current workdir without checking out a commit",
)
@click.option(
    "--tag", multiple=True, help="Specify tag as key=value. Can be used multiple times."
)
@click.option(
    "--log-level", default="INFO", help="Log level", type=click.Choice(LOG_LEVELS.keys())
)
def run(
    worktree,
    start_commit,
    end_commit,
    clone_url,
    es_url,
    es_user,
    es_password,
    delete_output_files,
    delete_repo,
    randomize,
    timing,
    tracemalloc,
    bench_pattern,
    as_is,
    tag,
    log_level,
):
    logging.basicConfig(level=LOG_LEVELS[log_level])
    if as_is and (start_commit or end_commit):
        raise click.ClickException(
            "--as-is can not be used with --start-commit and/or --end-commit"
        )
    if clone_url:
        if not os.path.exists(worktree):
            subprocess.check_output(["git", "clone", clone_url, worktree])
    if not as_is:
        subprocess.check_output(
            ["git", "fetch"], cwd=worktree, stderr=subprocess.STDOUT
        )
        subprocess.check_output(
            ["git", "checkout", "main"], cwd=worktree, stderr=subprocess.STDOUT
        )
    commits = get_commit_list(start_commit, end_commit, worktree)
    if tag:
        tags = {k: v for k, v in (item.split("=", 1) for item in tag)}
    else:
        tags = {}
    json_files = []
    failed = []
    if randomize:
        random.shuffle(commits)
    for i, commit in enumerate(commits):
        if len(commits) > 1:
            print(
                "Running bench for commit {} ({} of {})".format(
                    commit["sha"][:8], i + 1, len(commits)
                )
            )
        try:
            files = run_benchmark(
                commit, worktree, timing, tracemalloc, bench_pattern, as_is
            )
            if es_url:
                print("Uploading bench for commit {}".format(commit["sha"][:8]))
                upload_benchmark(es_url, es_user, es_password, files, commit, tags)
            json_files.extend(files)
        except subprocess.CalledProcessError as exc:
            failed.append(commit["sha"])
            logger.error(f"Commit {commit['sha']} failed. Output of runbench.py: \n{exc.output.decode()}")
        except Exception:
            failed.append(commit["sha"])
            logger.exception(f"Commit {commit['sha']} failed")
    if delete_repo:
        shutil.rmtree(worktree)
    if delete_output_files:
        for file in json_files:
            os.unlink(file)
    if failed:
        print("Failed commits: \n")
        for commit in failed:
            print(commit)
        print()


if __name__ == "__main__":
    run()
