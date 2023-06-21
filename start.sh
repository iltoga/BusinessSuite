#!/bin/bash

# Dynamically set the PYTHONPATH to include the project root
# SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# export PYTHONPATH="${PYTHONPATH}:${SCRIPT_DIR}"

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create groups
python manage.py creategroups

# Populate holidays
python manage.py populateholiday

# Populate document types
# python manage.py populate_documenttypes
python manage.py import_model fixtures/document_types.json
python manage.py import_model fixtures/products.json
python manage.py import_model fixtures/tasks.json

# Populate country codes
python manage.py populatecountrycodes

# Create superuser if none exists
python manage.py createsuperuserifnotexists

# Run Gunicorn
gunicorn RevisBaliCRM.wsgi:application --bind 0.0.0.0:8000 --log-file -
