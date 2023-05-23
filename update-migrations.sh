#!/bin/bash

# python manage.py createsuperuser
python manage.py makemigrations
python manage.py migrate
