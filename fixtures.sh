#!/bin/bash

# Load environment variables from .env file
if [ -f ".env" ]
then
  export $(cat ".env" | sed 's/#.*//g' | xargs)
fi

python manage.py populateholiday
python manage.py populatecountrycodes
python manage.py import_model fixtures/document_types.json
python manage.py import_model fixtures/products.json
python manage.py import_model fixtures/tasks.json
