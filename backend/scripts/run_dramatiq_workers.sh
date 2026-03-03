#!/bin/sh
set -eu

HIGH_PROCESSES="${DRAMATIQ_HIGH_PROCESSES:-1}"
HIGH_THREADS="${DRAMATIQ_HIGH_THREADS:-8}"
LOW_PROCESSES="${DRAMATIQ_LOW_PROCESSES:-1}"
LOW_THREADS="${DRAMATIQ_LOW_THREADS:-2}"
DRAMATIQ_BIN="${DRAMATIQ_BIN:-/opt/venv/bin/dramatiq}"

if [ ! -x "${DRAMATIQ_BIN}" ]; then
  echo "Dramatiq binary not found or not executable: ${DRAMATIQ_BIN}" >&2
  exit 127
fi

"${DRAMATIQ_BIN}" business_suite.dramatiq \
  --queues realtime default \
  --processes "${HIGH_PROCESSES}" \
  --threads "${HIGH_THREADS}" &
PID_HIGH=$!

"${DRAMATIQ_BIN}" business_suite.dramatiq \
  --queues scheduled low \
  --processes "${LOW_PROCESSES}" \
  --threads "${LOW_THREADS}" &
PID_LOW=$!

cleanup() {
  kill "${PID_HIGH}" "${PID_LOW}" 2>/dev/null || true
}

trap cleanup INT TERM

while true; do
  if ! kill -0 "${PID_HIGH}" 2>/dev/null; then
    wait "${PID_HIGH}" || STATUS=$?
    STATUS="${STATUS:-1}"
    kill "${PID_LOW}" 2>/dev/null || true
    wait "${PID_LOW}" 2>/dev/null || true
    exit "${STATUS}"
  fi

  if ! kill -0 "${PID_LOW}" 2>/dev/null; then
    wait "${PID_LOW}" || STATUS=$?
    STATUS="${STATUS:-1}"
    kill "${PID_HIGH}" 2>/dev/null || true
    wait "${PID_HIGH}" 2>/dev/null || true
    exit "${STATUS}"
  fi

  sleep 1
done
