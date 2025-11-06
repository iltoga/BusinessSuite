#!/usr/bin/env bash
set -euo pipefail

# Load environment variables
set -a
source .env
set +a

# Variables
DUMP_FILE="${1:-postgres15_dump.sql}"
CONTAINER_NAME="postgres-srv"
CONTAINER_PATH="/tmp/postgres_restore.sql"

# Validate dump file
if [ ! -f "$DUMP_FILE" ]; then
  echo "❌ Dump file '$DUMP_FILE' not found!"
  echo "Usage: ./restore_postgres18.sh path/to/postgres15_dump.sql"
  exit 1
fi

echo "🔹 Copying dump file into container '$CONTAINER_NAME'..."
docker cp "$DUMP_FILE" "$CONTAINER_NAME":"$CONTAINER_PATH"

echo "🔹 Ensuring target role '$POSTGRES_USER' exists..."
docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d postgres -c \
  "DO \$\$ BEGIN
