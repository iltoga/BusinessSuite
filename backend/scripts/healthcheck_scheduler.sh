#!/bin/sh
# Docker healthcheck for bs-scheduler container.
# Verifies:
#   1. The scheduler management command process is alive
#   2. Redis broker is reachable
set -e

PYTHON_BIN="${PYTHON_BIN:-/opt/venv/bin/python}"
MAX_HEARTBEAT_AGE_SECONDS="${DRAMATIQ_SCHEDULER_HEALTHCHECK_MAX_AGE_SECONDS:-60}"

# Check 1: Scheduler process alive
# The scheduler runs as: python manage.py run_dramatiq_scheduler
if ! pgrep -f "run_dramatiq_scheduler" > /dev/null 2>&1; then
  echo "[HEALTH] Scheduler process not found"
  exit 1
fi

# Check 2: Redis broker reachable and scheduler heartbeat fresh
"$PYTHON_BIN" -c "
import sys
import time
try:
    from django.conf import settings
    from core.services.redis_client import get_redis_client
    r = get_redis_client(socket_connect_timeout=3, socket_timeout=3)
    r.ping()
    key = getattr(settings, 'DRAMATIQ_SCHEDULER_HEARTBEAT_KEY', 'dramatiq:scheduler:heartbeat')
    raw = r.get(key)
    if raw is None:
        print(f'[HEALTH] Scheduler heartbeat missing: {key}')
        sys.exit(1)
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8')
    age = time.time() - float(raw)
    if age > float('$MAX_HEARTBEAT_AGE_SECONDS'):
        print(f'[HEALTH] Scheduler heartbeat stale ({age:.0f}s)')
        sys.exit(1)
except Exception as e:
    print(f'[HEALTH] Scheduler Redis/heartbeat check failed: {e}')
    sys.exit(1)
"

exit 0
