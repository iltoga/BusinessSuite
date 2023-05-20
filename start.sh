#!/bin/bash

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Run Gunicorn
gunicorn RevisBaliCRM.wsgi:application --bind 0.0.0.0:8000 --log-file -
