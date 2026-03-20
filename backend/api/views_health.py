"""
Unauthenticated health-check endpoint for Docker / load-balancer probes.

Returns lightweight JSON indicating whether the Django process, database and
Redis cache are reachable.  No sensitive data is exposed.

Docker healthcheck usage (no auth required):
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/', timeout=5)"
"""

import logging
import time

from django.db import close_old_connections, connection
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger("core")


class HealthCheckView(APIView):
    """Unauthenticated deep health probe for Docker / orchestrator use."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    throttle_classes: list = []

    def get(self, request: Request) -> Response:
        checks: dict[str, bool] = {}
        details: dict[str, str] = {}
        t0 = time.monotonic()

        def _check_database() -> None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

        # --- Database ---
        # Close stale/broken connections first so the probe creates a fresh one.
        if not getattr(connection, "in_atomic_block", False):
            try:
                close_old_connections()
            except Exception:
                pass

        try:
            _check_database()
            checks["db"] = True
        except Exception as exc:
            retry_exc = exc
            # `close_old_connections()` can leave us with a stale closed PostgreSQL
            # connection in test/dev setups. Force a reconnect once before failing.
            if "connection already closed" in str(exc).lower() and not getattr(connection, "in_atomic_block", False):
                try:
                    connection.close()
                except Exception:
                    pass
                try:
                    _check_database()
                    checks["db"] = True
                except Exception as retry_exc_2:
                    retry_exc = retry_exc_2
                    checks["db"] = False
            else:
                checks["db"] = False

            if not checks["db"]:
                details["db"] = str(retry_exc)[:200]
                logger.warning("[HEALTH] Database check failed: %s", retry_exc)
                # Force-close the broken connection so the next request gets a fresh one
                if not getattr(connection, "in_atomic_block", False):
                    try:
                        connection.close()
                    except Exception:
                        pass

        # --- Redis cache ---
        try:
            from django.core.cache import cache

            cache.set("_health_probe", "1", timeout=10)
            val = cache.get("_health_probe")
            checks["redis"] = val == "1"
            if not checks["redis"]:
                details["redis"] = "set/get round-trip mismatch"
                logger.warning("[HEALTH] Redis round-trip mismatch")
        except Exception as exc:
            checks["redis"] = False
            details["redis"] = str(exc)[:200]
            logger.warning("[HEALTH] Redis check failed: %s", exc)

        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        healthy = all(checks.values())

        payload = {
            "status": "healthy" if healthy else "unhealthy",
            "checks": checks,
            "elapsed_ms": elapsed_ms,
        }
        if details:
            payload["details"] = details

        http_status = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE

        if not healthy:
            logger.error("[HEALTH] Unhealthy: %s", payload)

        return Response(payload, status=http_status)
