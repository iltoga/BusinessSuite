#!/bin/sh
# Docker healthcheck for bs-worker container.
# Verifies:
#   1. The Dramatiq heartbeat file is fresh (updated within last 60s)
#   2. Redis broker is reachable
set -e

HEARTBEAT_FILE="/tmp/dramatiq_heartbeat"
MAX_AGE_SECONDS=60
REDIS_HOST="${REDIS_HOST:-bs-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
PYTHON_BIN="${PYTHON_BIN:-/opt/venv/bin/python}"

# Check 1: Heartbeat freshness
if [ ! -f "$HEARTBEAT_FILE" ]; then
  echo "[HEALTH] Worker heartbeat file not found"
  exit 1
fi

if [ -x "$(command -v find)" ]; then
  STALE=$(find "$HEARTBEAT_FILE" -mmin +1 2>/dev/null)
  if [ -n "$STALE" ]; then
    echo "[HEALTH] Worker heartbeat stale (>60s)"
    exit 1
  fi
else
  # Fallback: use python for age check
  "$PYTHON_BIN" -c "
import os, sys, time
age = time.time() - os.path.getmtime('$HEARTBEAT_FILE')
if age > $MAX_AGE_SECONDS:
    print(f'[HEALTH] Worker heartbeat stale ({age:.0f}s)')
    sys.exit(1)
"
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
