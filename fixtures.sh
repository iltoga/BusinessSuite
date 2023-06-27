#!/bin/bash
python manage.py import_model fixtures/document_types.json
python manage.py import_model fixtures/products.json
python manage.py import_model fixtures/tasks.json
