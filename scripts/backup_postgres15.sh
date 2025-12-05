#!/usr/bin/env bash
set -euo pipefail

BACKUP_NAME="postgres15_dump_$(date +%Y%m%d_%H%M%S).sql"
HOST_PATH="./${BACKUP_NAME}"

echo "🔹 Dumping all databases from container: postgres-srv"
docker exec -t postgres-srv pg_dumpall -U postgres > "$HOST_PATH"

echo "✅ Backup complete: $HOST_PATH"
