from benchmarks.decorators import with_elasticapm_client


@with_elasticapm_client()
def bench_capture_exception(client):
    try:
        assert False
    except AssertionError:
        client.capture_exception()
