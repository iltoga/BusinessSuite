#!/usr/bin/env bash
set -u

local_pg_restore="${DBBACKUP_LOCAL_PG_RESTORE:-pg_restore}"
docker_bin="${DBBACKUP_DOCKER_BIN:-docker}"
docker_container="${DBBACKUP_PGTOOLS_CONTAINER:-postgres-srv}"

tmp_dump_file="$(mktemp)"
tmp_stderr_file="$(mktemp)"

cleanup() {
  rm -f "$tmp_dump_file" "$tmp_stderr_file"
}
trap cleanup EXIT

# Keep stdin replayable so we can retry with dockerized pg_restore if needed.
cat >"$tmp_dump_file"

run_docker_pg_restore() {
  exec "$docker_bin" exec -e "PGPASSWORD=${PGPASSWORD:-}" -i "$docker_container" pg_restore "$@" <"$tmp_dump_file"
}

if command -v "$local_pg_restore" >/dev/null 2>&1; then
  if "$local_pg_restore" "$@" <"$tmp_dump_file" 2>"$tmp_stderr_file"; then
    exit 0
  fi

  local_status=$?
  local_stderr="$(cat "$tmp_stderr_file")"

  if printf '%s' "$local_stderr" | grep -Eqi "server version mismatch|unsupported version"; then
    echo "pg_restore version mismatch detected, retrying with Docker client from '$docker_container'." >&2
    run_docker_pg_restore "$@"
  fi

  printf '%s\n' "$local_stderr" >&2
  exit "$local_status"
fi

echo "Local pg_restore command '$local_pg_restore' not found, retrying with Docker client from '$docker_container'." >&2
run_docker_pg_restore "$@"
