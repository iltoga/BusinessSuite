#!/bin/sh
# Docker healthcheck for bs-scheduler container.
# Verifies:
#   1. The scheduler management command process is alive
#   2. Redis broker is reachable
set -e

PYTHON_BIN="${PYTHON_BIN:-/opt/venv/bin/python}"
REDIS_HOST="${REDIS_HOST:-bs-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

# Check 1: Scheduler process alive
# The scheduler runs as: python manage.py run_dramatiq_scheduler
if ! pgrep -f "run_dramatiq_scheduler" > /dev/null 2>&1; then
  echo "[HEALTH] Scheduler process not found"
  exit 1
fi

# Check 2: Redis broker reachable
"$PYTHON_BIN" -c "
import sys
try:
    import redis
    r = redis.Redis(host='$REDIS_HOST', port=$REDIS_PORT, socket_connect_timeout=3, socket_timeout=3)
    r.ping()
except Exception as e:
    print(f'[HEALTH] Redis unreachable: {e}')
    sys.exit(1)
"

exit 0
