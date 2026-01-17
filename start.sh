#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# 1. Load environment variables from .env if it exists (fallback for local/non-compose runs)
if [ -f .env ]; then
  echo "Loading variables from .env file..."
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# 2. Safety Check for Required Variables
if [[ -z "${SYSTEM_USER_PASSWORD}" || -z "${SYSTEM_USER_EMAIL}" ]]; then
  echo "Error: SYSTEM_USER_PASSWORD or SYSTEM_USER_EMAIL is not set."
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

# 4. Database Initialization
if [[ "${RESET_DB_ON_STARTUP}" == "true" ]]; then
  echo "Clearing database as requested..."
  python manage.py flush --noinput
fi

# 5. Core Django Operations
echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Compiling translations..."
python manage.py compilemessages || echo "Warning: compilemessages skipped (msgfmt might be missing)"

# 6. Data Seeding & User Setup
echo "Populating initial data..."
python manage.py creategroups
python manage.py populate_documenttypes
python manage.py populate_products
python manage.py populate_tasks
python manage.py populatecountrycodes
python manage.py populateholiday

echo "Setting up users..."
python manage.py createsuperuserifnotexists
python manage.py create_user system "$SYSTEM_USER_PASSWORD" --superuser --email="$SYSTEM_USER_EMAIL" || echo "System user already exists."

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