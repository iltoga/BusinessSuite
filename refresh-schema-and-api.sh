#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
DJANGO_SETTINGS_MODULE_VALUE="${DJANGO_SETTINGS_MODULE:-business_suite.settings}"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="python"
fi

echo "Generating backend/schema.yaml via Django schema command..."
(
  cd "$BACKEND_DIR"
  DJANGO_SETTINGS_MODULE="$DJANGO_SETTINGS_MODULE_VALUE" "$PYTHON_BIN" manage.py generate_frontend_schema \
    --output schema.yaml \
    --validate \
    --fail-on-warn
)

echo "Generating frontend API client..."
(
  cd "$FRONTEND_DIR"
  bun run generate:api
)

echo "Done."
