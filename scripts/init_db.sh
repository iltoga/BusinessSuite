#!/usr/bin/env bash
set -euo pipefail

# Helper script to initialize and seed the database. Intended to be run
# as a one-off via the deploy workflow or via docker-compose run --rm.

# Inside Docker, use the virtualenv python if available
PYTHON_BIN="python"
if [ -x "/opt/venv/bin/python" ]; then
    PYTHON_BIN="/opt/venv/bin/python"
fi

echo "Populating initial data..."
$PYTHON_BIN manage.py creategroups
$PYTHON_BIN manage.py populate_documenttypes
$PYTHON_BIN manage.py populate_products
$PYTHON_BIN manage.py populate_tasks
$PYTHON_BIN manage.py populatecountrycodes
$PYTHON_BIN manage.py populateholiday

echo "Setting up users..."
$PYTHON_BIN manage.py createsuperuserifnotexists
$PYTHON_BIN manage.py create_user system "${SYSTEM_USER_PASSWORD:-}" --superuser --email="${SYSTEM_USER_EMAIL:-}" || echo "System user already exists."

echo "Database initialization complete."