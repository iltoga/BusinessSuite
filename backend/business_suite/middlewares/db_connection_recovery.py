"""
Middleware that closes broken database connections before request processing.

In Docker environments, transient DNS failures or container restarts can leave
Django's persistent connections (CONN_MAX_AGE > 0) in a broken state.  When
this happens, every subsequent request on that Gunicorn worker fails with
``OperationalError`` until the stale connection ages out or the worker recycles.

This middleware calls ``close_old_connections()`` at the start of each request,
which checks connection health and drops any that fail the liveness probe.
Combined with ``CONN_HEALTH_CHECKS = True``, this ensures the next query gets a
fresh connection.
"""

from django.db import close_old_connections
from django.utils.deprecation import MiddlewareMixin


class DbConnectionRecoveryMiddleware(MiddlewareMixin):
    def process_request(self, request):
        close_old_connections()
