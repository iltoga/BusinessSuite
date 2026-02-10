#!/bin/bash

# Use the virtualenv python if available
PYTHON_BIN="python"
if [ -x "/opt/venv/bin/python" ]; then
    PYTHON_BIN="/opt/venv/bin/python"
fi

$PYTHON_BIN manage.py cleardb
$PYTHON_BIN manage.py clear_migrations
