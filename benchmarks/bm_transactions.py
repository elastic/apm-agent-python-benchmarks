from elasticapm import capture_span

from benchmarks.decorators import with_elasticapm_client


@with_elasticapm_client()
def bench_transaction_no_spans(client):
    client.begin_transaction("test")
    client.end_transaction("test", "OK")


@with_elasticapm_client(
    span_frames_min_duration_ms=0,
    source_lines_span_app_frames=3,
    source_lines_span_library_frames=3,
)
def bench_transaction_spans(client):
    client.begin_transaction("test")
    with capture_span("test1"):
        with capture_span("test2"):
            with capture_span("test3"):
                pass
    client.end_transaction("test", "OK")
