#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# 1. Load environment variables from .env.
# - Outside Docker: source all vars from .env (existing behavior).
# - Inside Docker: import ONLY vars that are currently missing so explicit
#   Compose/container env values always win.
if [ -f .env ]; then
  if [ -f "/.dockerenv" ]; then
    echo "Docker runtime detected: importing missing variables from .env (without overriding existing env)."
    while IFS= read -r line || [ -n "$line" ]; do
      # Skip comments and empty lines
      [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
      # Support optional `export KEY=VALUE` prefix
      line="${line#export }"
      # Keep only KEY=VALUE lines
      [[ "$line" != *=* ]] && continue

      key="${line%%=*}"
      value="${line#*=}"

      # Trim whitespace around key
      key="$(echo "$key" | xargs)"
      [[ -z "$key" ]] && continue

      # If already present in environment, do not override
      if [ -n "${!key+x}" ]; then
        continue
      fi

      # Trim surrounding single/double quotes from value
      value="${value#\"}"
      value="${value%\"}"
      value="${value#\'}"
      value="${value%\'}"

      export "$key=$value"
    done < .env
  else
    echo "Loading variables from .env file..."
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
  fi
fi

# 2. Startup sanity checks
# SYSTEM_USER_* variables are only required by scripts/init_db.sh (optional one-off seeding).
# They should not block normal web startup.
if [[ -z "${SYSTEM_USER_PASSWORD:-}" || -z "${SYSTEM_USER_EMAIL:-}" ]]; then
  echo "Warning: SYSTEM_USER_PASSWORD or SYSTEM_USER_EMAIL is not set; skipping system-user validation during web startup."
fi

# 3. Wait for Database (Optional but highly recommended for Docker)
# This prevents the app from crashing if the DB container isn't ready yet
if [ -n "$DB_HOST" ]; then
  echo "Waiting for database at $DB_HOST..."
  until printf "" 2>>/dev/null >>/dev/tcp/$DB_HOST/${DB_PORT:-5432}; do
    echo "Database unavailable - sleeping..."
    sleep 1
  done
  echo "Database is up!"
fi

# Inside Docker, use the virtualenv python if available
PYTHON_BIN="python"
if [ -x "/opt/venv/bin/python" ]; then
    PYTHON_BIN="/opt/venv/bin/python"
fi

# 4. Database Initialization
if [[ "${RESET_DB_ON_STARTUP}" == "true" ]]; then
  echo "Clearing database as requested..."
  $PYTHON_BIN manage.py flush --noinput
fi

# 5. Core Django Operations
echo "Running migrations..."
$PYTHON_BIN manage.py migrate --noinput

echo "Collecting static files..."
$PYTHON_BIN manage.py collectstatic --noinput --clear

echo "Compiling translations..."
$PYTHON_BIN manage.py compilemessages || echo "Warning: compilemessages skipped (msgfmt might be missing)"

# 6. Data Seeding & User Setup
# NOTE: Database initialization logic has been moved to the deploy workflow
# (see .github/workflows/deploy.yml) and is executed as a one-off job using
# the helper script `scripts/init_db.sh` to keep initialization auditable
# and avoid accidental re-runs on container restart.
# Examples:
#  - From CI/deploy: the workflow will run `docker compose run --rm bs-core bash -lc "bash /usr/src/app/scripts/init_db.sh"`
#  - Manual one-off: `docker compose run --rm bs-core bash -lc "bash /usr/src/app/scripts/init_db.sh"`
# If you need to run initialization from inside the container manually,
# run: bash /usr/src/app/scripts/init_db.sh


# 7. Start Gunicorn
# Optimization: --worker-tmp-dir /dev/shm prevents heartbeat blocking on disk I/O
# Optimization: gthread is best for the mixed I/O (Database) and API (LLM/OpenAI) profile
GUNICORN_BIND="${GUNICORN_BIND:-0.0.0.0:8000}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-4}"
GUNICORN_THREADS="${GUNICORN_THREADS:-2}"
GUNICORN_WORKER_CLASS="${GUNICORN_WORKER_CLASS:-gthread}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-120}"
GUNICORN_MAX_REQUESTS="${GUNICORN_MAX_REQUESTS:-1200}"
GUNICORN_MAX_REQUESTS_JITTER="${GUNICORN_MAX_REQUESTS_JITTER:-50}"
GUNICORN_LOG_LEVEL="${GUNICORN_LOG_LEVEL:-info}"

echo "Starting Gunicorn..."
exec gunicorn business_suite.wsgi:application \
  --bind "${GUNICORN_BIND}" \
  --no-control-socket \
  --workers "${GUNICORN_WORKERS}" \
  --threads "${GUNICORN_THREADS}" \
  --worker-class "${GUNICORN_WORKER_CLASS}" \
  --timeout "${GUNICORN_TIMEOUT}" \
  --max-requests "${GUNICORN_MAX_REQUESTS}" \
  --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER}" \
  --worker-tmp-dir /dev/shm \
  --access-logfile - \
  --error-logfile - \
  --log-level "${GUNICORN_LOG_LEVEL}"
