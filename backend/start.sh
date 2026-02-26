#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# 1. Load environment variables from .env only outside Docker.
# In containerized runs, Compose already injects env vars and should not be
# overridden by repository-local .env values.
if [ -f .env ]; then
  if [ -f "/.dockerenv" ]; then
    echo "Skipping .env load inside Docker; using container environment variables."
  else
    echo "Loading variables from .env file..."
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
  fi
fi

# 2. Safety Check for Required Variables
if [[ -z "${SYSTEM_USER_PASSWORD}" || -z "${SYSTEM_USER_EMAIL}" ]]; then
  echo "Error: SYSTEM_USER_PASSWORD or SYSTEM_USER_EMAIL is not set."
  echo "DEBUG: SYSTEM_USER_PASSWORD value: [${SYSTEM_USER_PASSWORD}]"
  echo "DEBUG: SYSTEM_USER_EMAIL value: [${SYSTEM_USER_EMAIL}]"
  echo "DEBUG: Current User: $(id)"
  echo "DEBUG: PWD: $PWD"
  echo "DEBUG: Directory listing of $PWD:"
  ls -la
  if [ -f .env ]; then
    echo "DEBUG: .env file FOUND in $PWD"
    echo "DEBUG: .env keys present:"
    grep -o '^[A-Z_]*' .env | sort | xargs
  else
    echo "DEBUG: .env file NOT FOUND in $PWD"
  fi
  exit 1
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
echo "Starting Gunicorn..."
exec gunicorn business_suite.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 4 \
  --threads 2 \
  --worker-class gthread \
  --timeout 120 \
  --max-requests 1200 \
  --max-requests-jitter 50 \
  --worker-tmp-dir /dev/shm \
  --access-logfile - \
  --error-logfile - \
  --log-level info
