#!/usr/bin/env bash
set -u

local_pg_dump="${DBBACKUP_LOCAL_PG_DUMP:-pg_dump}"
docker_bin="${DBBACKUP_DOCKER_BIN:-docker}"
docker_container="${DBBACKUP_PGTOOLS_CONTAINER:-postgres-srv}"

run_docker_pg_dump() {
  exec "$docker_bin" exec -e "PGPASSWORD=${PGPASSWORD:-}" -i "$docker_container" pg_dump "$@"
}

if command -v "$local_pg_dump" >/dev/null 2>&1; then
  stderr_file="$(mktemp)"
  if "$local_pg_dump" "$@" 2>"$stderr_file"; then
    rm -f "$stderr_file"
    exit 0
  fi

  local_status=$?
  local_stderr="$(cat "$stderr_file")"
  rm -f "$stderr_file"

  if printf '%s' "$local_stderr" | grep -qi "server version mismatch"; then
    echo "pg_dump server/client mismatch detected, retrying with Docker client from '$docker_container'." >&2
    run_docker_pg_dump "$@"
  fi

  printf '%s\n' "$local_stderr" >&2
  exit "$local_status"
fi

echo "Local pg_dump command '$local_pg_dump' not found, retrying with Docker client from '$docker_container'." >&2
run_docker_pg_dump "$@"
