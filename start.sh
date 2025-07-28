#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]
then
  export $(cat .env | sed 's/#.*//g' | xargs)
fi

# Check if SYSTEM_USER_PASSWORD and SYSTEM_USER_EMAIL are set and not empty
if [[ -z "${SYSTEM_USER_PASSWORD}" ]]; then
  echo "Error: SYSTEM_USER_PASSWORD is not set or empty. Please set the SYSTEM_USER_PASSWORD environment variable."
  exit 1
fi
if [[ -z "${SYSTEM_USER_EMAIL}" ]]; then
  echo "Error: SYSTEM_USER_EMAIL is not set or empty. Please set the SYSTEM_USER_EMAIL environment variable."
  exit 1
fi

# Dynamically set the PYTHONPATH to include the project root
# SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# export PYTHONPATH="${PYTHONPATH}:${SCRIPT_DIR}"

# Check if database should be reset
if [[ "${RESET_DB_ON_STARTUP}" == "true" ]]; then
  echo "RESET_DB_ON_STARTUP is set to true. Clearing database..."
  python manage.py cleardb
  echo "Database cleared successfully."
fi

# Run migrations
python manage.py migrate

# Create groups
python manage.py creategroups

# Populate database with essential data
python manage.py populate_documenttypes
python manage.py populate_products
python manage.py populate_tasks
python manage.py populatecountrycodes
python manage.py populateholiday

# Create superuser if none exists
python manage.py createsuperuserifnotexists

# Create system user
python manage.py create_user system $SYSTEM_USER_PASSWORD --superuser --email=$SYSTEM_USER_EMAIL

# Collect static files
python manage.py collectstatic --noinput

# Run Gunicorn
gunicorn business_suite.wsgi:application --bind 0.0.0.0:8000 --log-file -
