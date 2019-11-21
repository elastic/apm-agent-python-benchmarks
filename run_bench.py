import fnmatch
import functools
import importlib
import operator
import os
import pkgutil
import sys
import time
import tracemalloc

import benchmarks
import elasticapm
import pyperf


def discover_benchmarks():
    for importer, modname, is_pkg in sorted(
        pkgutil.iter_modules(benchmarks.__path__), key=operator.itemgetter(1)
    ):
        if modname.startswith("bm_"):
            bench_module = importlib.import_module("benchmarks." + modname)
            for func_name in sorted(dir(bench_module)):
                if func_name.startswith("bench_"):
                    yield getattr(bench_module, func_name)


def run():
    metadata = {}
    if "COMMIT_TIMESTAMP" in os.environ:
        metadata["timestamp"] = os.environ.get("COMMIT_TIMESTAMP")
        metadata["revision"] = os.environ.get("COMMIT_SHA")
        metadata["commit_message"] = os.environ.get("COMMIT_MESSAGE").split("\n")[0]
    runner = pyperf.Runner(metadata=metadata)
    pattern = os.environ.get("BENCH_PATTERN")

    args = runner.parse_args()
    if args.tracemalloc:
        bench_type = "tracemalloc"
    elif args.track_memory:
        bench_type = "trackmem"
    else:
        bench_type = "time"
    for func in discover_benchmarks():
        name = "%s.%s.%s" % (str(func.__module__), func.__name__, bench_type)
        if not pattern or fnmatch.fnmatch(name, pattern):
            client = None
            if hasattr(func, "client_defaults"):
                # create the client outside of the benchmarked function
                client = elasticapm.Client(**func.client_defaults)
                func = functools.partial(func, client=client)
                if args.tracemalloc:
                    tracemalloc.clear_traces()
            runner.bench_func(name, func)
            if client:
                client.close()


if __name__ == "__main__":
    run()
