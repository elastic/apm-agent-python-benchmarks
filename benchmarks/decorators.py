import functools


class with_elasticapm_client:
    def __init__(self, **client_defaults):
        client_defaults.setdefault("disable_send", True)
        client_defaults.setdefault("service_name", "benchmarks")
        self.client_defaults = client_defaults

    def __call__(self, f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            f(*args, **kwargs)

        wrapped.client_defaults = self.client_defaults
        return wrapped
