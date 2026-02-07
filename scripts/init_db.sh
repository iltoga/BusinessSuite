#!/usr/bin/env bash
set -euo pipefail

# Helper script to initialize and seed the database. Intended to be run
# as a one-off via the deploy workflow or via docker-compose run --rm.

echo "Populating initial data..."
python manage.py creategroups
python manage.py populate_documenttypes
python manage.py populate_products
python manage.py populate_tasks
python manage.py populatecountrycodes
python manage.py populateholiday

echo "Setting up users..."
python manage.py createsuperuserifnotexists
python manage.py create_user system "${SYSTEM_USER_PASSWORD:-}" --superuser --email="${SYSTEM_USER_EMAIL:-}" || echo "System user already exists."

echo "Database initialization complete."