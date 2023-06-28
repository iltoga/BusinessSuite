#!/bin/bash

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Get the parent directory of the script
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment variables from .env file
if [ -f "${PARENT_DIR}/.env" ]
then
  export $(cat "${PARENT_DIR}/.env" | sed 's/#.*//g' | xargs)
fi

MANAGE="${PARENT_DIR}/manage.py"

# Populate holidays
python "${MANAGE}" populateholiday
# Populate country codes
python "${MANAGE}" populatecountrycodes
# Populate document types
python "${MANAGE}" import_model fixtures/document_types.json
# Populate product types
python "${MANAGE}" import_model fixtures/product_types.json
# Populate task types
python "${MANAGE}" import_model fixtures/task_types.json
