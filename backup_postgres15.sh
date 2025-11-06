#!/usr/bin/env bash
set -euo pipefail

# Load environment variables
set -a
source .env
set +a

BACKUP_NAME="postgres15_dump_$(date +%Y%m%d_%H%M%S).sql"
TMP_PATH="/tmp/${BACKUP_NAME}"
HOST_PATH="./${BACKUP_NAME}"

echo "🔹 Dumping all databases from container: postgres-srv"
docker exec -t postgres-srv pg_dumpall -U "$DB_USER" > "$TMP_PATH"

echo "🔹 Copying dump to host..."
docker cp postgres-srv:"$TMP_PATH" "$HOST_PATH"

echo "✅ Backup complete: $HOST_PATH"
