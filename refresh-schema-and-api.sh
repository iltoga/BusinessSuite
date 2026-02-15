#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8000"
BACKEND_ADDR="${BACKEND_HOST}:${BACKEND_PORT}"
LOG_DIR="$ROOT_DIR/logs"
BACKEND_LOG_FILE="$LOG_DIR/schema-backend.log"
DJANGO_SETTINGS_MODULE_VALUE="${DJANGO_SETTINGS_MODULE:-business_suite.settings}"

STARTED_BACKEND=0
BACKEND_PID=""

port_is_listening() {
  lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1
}

cleanup() {
  if [[ "$STARTED_BACKEND" -eq 1 && -n "$BACKEND_PID" ]]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="python"
fi

if ! port_is_listening; then
  mkdir -p "$LOG_DIR"
  echo "Backend not running on ${BACKEND_ADDR}. Starting local Django server..."
  (
    cd "$BACKEND_DIR"
    exec env DJANGO_SETTINGS_MODULE="$DJANGO_SETTINGS_MODULE_VALUE" "$PYTHON_BIN" manage.py runserver "$BACKEND_ADDR"
  ) >"$BACKEND_LOG_FILE" 2>&1 &
  BACKEND_PID="$!"
  STARTED_BACKEND=1

  for _ in $(seq 1 60); do
    if port_is_listening; then
      break
    fi

    if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
      echo "Failed to start backend. Last lines from $BACKEND_LOG_FILE:"
      tail -n 40 "$BACKEND_LOG_FILE" || true
      exit 1
    fi
    sleep 1
  done

  if ! port_is_listening; then
    echo "Timed out waiting for backend on ${BACKEND_ADDR}."
    exit 1
  fi
fi

echo "Generating backend/schema.yaml via Django spectacular..."
(
  cd "$BACKEND_DIR"
  DJANGO_SETTINGS_MODULE="$DJANGO_SETTINGS_MODULE_VALUE" "$PYTHON_BIN" manage.py spectacular --file schema.yaml
)

echo "Generating frontend API client..."
(
  cd "$FRONTEND_DIR"
  bun run generate:api
)

echo "Done."
