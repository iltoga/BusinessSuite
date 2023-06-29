#!/bin/bash

# Load environment variables from .env file
if [ -f ".env" ]
then
  export $(cat ".env" | sed 's/#.*//g' | xargs)
fi

# Populate holidays
python manage.py populateholiday
# Populate country codes
python manage.py populatecountrycodes
# Populate document types
python manage.py import_model fixtures/document_types.json
# Populate product types
python manage.py import_model fixtures/products.json
# Populate task types
python manage.py import_model fixtures/tasks.json
