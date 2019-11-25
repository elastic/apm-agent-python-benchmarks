# Benchmarks for the Elastic APM Python agent

This repository contains the benchmark suite for the Elastic APM Python agent.
It uses [`pyperf`](https://pypi.org/project/pyperf/) to run the benchmarks.

## Writing a benchmark

Benchmarks are callables that are auto-discovered by the runner.
To be discovered, the callables have to

 *  be prefixed with `bench_`:
 
         def bench_something():
             # code to be benchmarked
 * live in a module that is prefixed with `bm_`, e.g. `bm_mybenches.py`
 * that module has to be in the `benchmarks` package
 
If your benchmark needs an `elasticapm.Client` instance, use the `benchmarks.decorators.with_elasticapm_client` decorator.
The decorator will instantiate the client outside of your benchmark function.
This ensures that client instantiation is not part of your benchmark.
You can pass configuration option to the client as keyword arguments to the decorator.

    from benchmarks.decorators import with_elasticapm_client
    
    @with_elasticapm_client(span_frame_min_duration=0)
    def bench_something(client):
        client.begin_transaction()
        # ...
        
# Running the benchmarks

First, install the requirements:

    pip install -r requirements.txt

As these benchmarks live in a separate repository, they need a checkout of the agent repository to run in.
You can use the `run_bench_commits.py` runner to create the repository, run the benchmarks on one or more commits,
and send the result to Elasticsearch:

    Usage: run_bench_commits.py [OPTIONS]
    
    Options:
      --worktree PATH                 worktree of elastic-apm to run benchmarks in
                                      [required]
      --start-commit TEXT             first commit to benchmark. If left empty,
                                      current worktree state will be benchmarked
      --end-commit TEXT               last commit to benchmark. If left empty,
                                      only start-commit will be benchmarked
      --clone-url TEXT                Git URL to clone
      --es-url TEXT                   Elasticsearch URL
      --es-user TEXT                  Elasticsearch User
      --es-password TEXT              Elasticsearch Password
      --delete-output-files / --no-delete-output-files
                                      Delete benchmark files
      --delete-repo / --no-delete-repo
                                      Delete repo after run
      --randomize / --no-randomize    Randomize order of commits
      --timing / --no-timing          Run timing benchmarks
      --tracemalloc / --no-tracemalloc
                                      Run tracemalloc benchmarks
      --bench-pattern TEXT            An optional glob pattern to filter
                                      benchmarks by
      --as-is                         Run benchmark in current workdir without
                                      checking out a commit
      --tag TEXT                      Specify tag as key=value
      --help                          Show this message and exit.
