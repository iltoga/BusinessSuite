#!/usr/bin/env bash
set -euo pipefail

# Load environment variables (optional, if you need DB_USER)
set -a
source .env
set +a

DUMP_FILE="${1:-postgres15_dump.sql}"

if [ ! -f "$DUMP_FILE" ]; then
  echo "❌ Dump file '$DUMP_FILE' not found!"
  echo "Usage: ./restore_postgres18.sh path/to/postgres15_dump.sql"
  exit 1
fi

echo "🔹 Restoring dump into postgres-srv container (PostgreSQL 18)..."
cat "$DUMP_FILE" | docker exec -i postgres-srv psql -U postgres

echo "✅ Restore complete. Checking version..."
docker exec -it postgres-srv psql -U postgres -c "SELECT version();"
