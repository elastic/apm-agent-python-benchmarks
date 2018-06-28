import sys
import functools

import elasticapm


class with_elasticapm_client():
    def __init__(self, **client_defaults):
        client_defaults.setdefault('disable_send', True)
        self.client_defaults = client_defaults

    def __call__(self, f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            client = elasticapm.Client(**self.client_defaults)
            kwargs['client'] = client
            if '--tracemalloc' in sys.argv:
                import tracemalloc
                tracemalloc.clear_traces()
            f(*args, **kwargs)
            client.close()
        return wrapped
