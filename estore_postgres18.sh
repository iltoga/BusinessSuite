#!/usr/bin/env bash
set -euo pipefail

# Load environment variables
set -a
source .env
set +a

DUMP_FILE="${1:-postgres15_dump.sql}"

if [ ! -f "$DUMP_FILE" ]; then
  echo "❌ Dump file '$DUMP_FILE' not found!"
  echo "Usage: ./restore_postgres18.sh path/to/postgres15_dump.sql"
  exit 1
fi

echo "🔹 Copying dump file into postgres-srv container..."
docker cp "$DUMP_FILE" postgres-srv:/tmp/postgres_restore.sql

echo "🔹 Restoring into database $DB_NAME..."
docker exec -i postgres-srv psql -U "$DB_USER" -d "$DB_NAME" -f /tmp/postgres_restore.sql

echo "✅ Restore complete. Checking version..."
docker exec -it postgres-srv psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT version();"
