#!/bin/bash

# python manage.py createsuperuser
python3 manage.py makemigrations --settings=RevisBaliCRM.settings.dev
python3 manage.py migrate --settings=RevisBaliCRM.settings.dev

python3 manage.py createsuperuserifnotexists --settings=RevisBaliCRM.settings.dev
python3 manage.py creategroups --settings=RevisBaliCRM.settings.dev