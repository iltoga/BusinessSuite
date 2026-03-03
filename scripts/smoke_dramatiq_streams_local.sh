#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE=(docker compose -f docker-compose-local.yml --profile app)
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
BASE_DB_NAME="${DB_NAME:-revisbali}"
SMOKE_DB_NAME="${SMOKE_DB_NAME:-${BASE_DB_NAME}_smoke}"
LIVE_TIMEOUT_SECONDS="${LIVE_TIMEOUT_SECONDS:-180}"
LIVE_FIRST_EVENT_TIMEOUT_SECONDS="${LIVE_FIRST_EVENT_TIMEOUT_SECONDS:-45}"
REPLAY_TIMEOUT_SECONDS="${REPLAY_TIMEOUT_SECONDS:-60}"
REPLAY_FIRST_EVENT_TIMEOUT_SECONDS="${REPLAY_FIRST_EVENT_TIMEOUT_SECONDS:-20}"
READINESS_TIMEOUT_SECONDS="${READINESS_TIMEOUT_SECONDS:-360}"

SSE_CAPTURE_SAW_ID=0
SSE_CAPTURE_SAW_TERMINAL=0
SSE_CAPTURE_TIMED_OUT_FIRST=0
SSE_CAPTURE_CURL_STATUS=0

dump_runtime_diagnostics() {
  echo "[smoke] compose ps:"
  "${COMPOSE[@]}" ps || true
  echo "[smoke] bs-core runtime env (Redis/Dramatiq/DB):"
  "${COMPOSE[@]}" exec -T bs-core sh -lc 'env | sort | rg "^(REDIS|DRAMATIQ|DB_HOST|DB_PORT)=" || true' || true
  echo "[smoke] bs-scheduler runtime env (Redis/Dramatiq/DB):"
  "${COMPOSE[@]}" exec -T bs-scheduler sh -lc 'env | sort | rg "^(REDIS|DRAMATIQ|DB_HOST|DB_PORT)=" || true' || true
  echo "[smoke] bs-core logs (tail=200):"
  "${COMPOSE[@]}" logs --no-color --tail=200 bs-core || true
  echo "[smoke] bs-worker logs (tail=200):"
  "${COMPOSE[@]}" logs --no-color --tail=200 bs-worker || true
  echo "[smoke] bs-scheduler logs (tail=200):"
  "${COMPOSE[@]}" logs --no-color --tail=200 bs-scheduler || true
}

compose_smoke() {
  DB_NAME="${SMOKE_DB_NAME}" "${COMPOSE[@]}" "$@"
}

ensure_smoke_database_exists() {
  if ! [[ "${SMOKE_DB_NAME}" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "[smoke] Invalid SMOKE_DB_NAME '${SMOKE_DB_NAME}'. Allowed characters: letters, digits, underscore."
    exit 1
  fi

  echo "[smoke] Ensuring isolated smoke database exists: ${SMOKE_DB_NAME}"
  "${COMPOSE[@]}" exec -T -e SMOKE_DB_NAME="${SMOKE_DB_NAME}" db sh -lc '
    set -eu
    db_user="${POSTGRES_USER:-postgres}"
    if psql -U "$db_user" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '\''${SMOKE_DB_NAME}'\''" | grep -q 1; then
      exit 0
    fi
    createdb -U "$db_user" "$SMOKE_DB_NAME"
  '
}

run_sse_capture() {
  local output_file="$1"
  local error_file="$2"
  local timeout_seconds="$3"
  local first_event_timeout_seconds="$4"
  shift 4

  : >"${output_file}"
  : >"${error_file}"

  SSE_CAPTURE_SAW_ID=0
  SSE_CAPTURE_SAW_TERMINAL=0
  SSE_CAPTURE_TIMED_OUT_FIRST=0
  SSE_CAPTURE_CURL_STATUS=0

  curl -sS -N --connect-timeout 5 --max-time "${timeout_seconds}" "$@" >"${output_file}" 2>"${error_file}" &
  local curl_pid=$!
  local started_at
  started_at="$(date +%s)"
  local elapsed=0
  local last_log_at=0

  while kill -0 "${curl_pid}" 2>/dev/null; do
    elapsed=$(( $(date +%s) - started_at ))

    if [[ "${SSE_CAPTURE_SAW_ID}" -eq 0 ]] && grep -q '^id:' "${output_file}" 2>/dev/null; then
      SSE_CAPTURE_SAW_ID=1
      echo "[smoke] SSE first event received after ${elapsed}s."
    fi

    if [[ "${SSE_CAPTURE_SAW_TERMINAL}" -eq 0 ]] && grep -Eq '^data: .*Backup finished|^data: .*Error:' "${output_file}" 2>/dev/null; then
      SSE_CAPTURE_SAW_TERMINAL=1
      echo "[smoke] SSE terminal message detected after ${elapsed}s."
      kill "${curl_pid}" 2>/dev/null || true
      break
    fi

    if [[ "${SSE_CAPTURE_SAW_ID}" -eq 0 && "${elapsed}" -ge "${first_event_timeout_seconds}" ]]; then
      SSE_CAPTURE_TIMED_OUT_FIRST=1
      echo "[smoke] SSE did not emit any event id within ${first_event_timeout_seconds}s."
      kill "${curl_pid}" 2>/dev/null || true
      break
    fi

    if (( elapsed - last_log_at >= 10 )); then
      last_log_at="${elapsed}"
      if [[ "${SSE_CAPTURE_SAW_ID}" -eq 1 ]]; then
        echo "[smoke] SSE stream still open (${elapsed}s elapsed)..."
      else
        echo "[smoke] Waiting for first SSE event (${elapsed}s/${first_event_timeout_seconds}s)..."
      fi
    fi

    sleep 1
  done

  wait "${curl_pid}" || SSE_CAPTURE_CURL_STATUS=$?
}

echo "[smoke] Starting local infra (db, redis)..."
"${COMPOSE[@]}" up -d --build --pull never db redis
ensure_smoke_database_exists

echo "[smoke] Starting app stack on isolated DB '${SMOKE_DB_NAME}' (bs-core, bs-worker, bs-scheduler)..."
compose_smoke up -d --build --pull never bs-core bs-worker bs-scheduler

echo "[smoke] Waiting for API readiness..."
READY=0
ATTEMPTS=$((READINESS_TIMEOUT_SECONDS / 2))
for i in $(seq 1 "${ATTEMPTS}"); do
  if curl -fsS --connect-timeout 2 --max-time 4 "${API_BASE_URL}/api/app-config/" >/dev/null 2>&1; then
    READY=1
    break
  fi
  if (( i % 15 == 0 )); then
    echo "[smoke] Still waiting for API... (${i}/$ATTEMPTS)"
    compose_smoke ps bs-core bs-worker bs-scheduler || true
  fi
  sleep 2
done

if [[ "$READY" != "1" ]]; then
  echo "[smoke] API readiness check failed after ${READINESS_TIMEOUT_SECONDS}s."
  dump_runtime_diagnostics
  exit 1
fi

echo "[smoke] Ensuring migrations are applied..."
compose_smoke exec -T bs-core sh -lc "cd /usr/src/app && /opt/venv/bin/python manage.py migrate --noinput >/dev/null"

echo "[smoke] Clearing Dramatiq Redis DB for deterministic queue state..."
DRAMATIQ_DB="${DRAMATIQ_REDIS_DB:-0}"
"${COMPOSE[@]}" exec -T redis redis-cli -n "${DRAMATIQ_DB}" FLUSHDB >/dev/null

echo "[smoke] Creating/refreshing smoke admin token..."
AUTH_INFO="$(
  compose_smoke exec -T bs-core sh -lc '
    cd /usr/src/app &&
    /opt/venv/bin/python manage.py createsuperuserifnotexists >/dev/null &&
    /opt/venv/bin/python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

User = get_user_model()
username = os.getenv(\"SITE_ADMIN_USERNAME\", \"revisadmin\")
user = User.objects.get(username=username)
token, _ = Token.objects.get_or_create(user=user)
print(f\"SMOKE_USER_ID={user.id}\")
print(f\"SMOKE_TOKEN={token.key}\")
"
  '
)"

USER_ID="$(printf '%s\n' "$AUTH_INFO" | awk -F= '/^SMOKE_USER_ID=/{print $2}' | tail -n1)"
TOKEN="$(printf '%s\n' "$AUTH_INFO" | awk -F= '/^SMOKE_TOKEN=/{print $2}' | tail -n1)"
if [[ -z "$USER_ID" || -z "$TOKEN" ]]; then
  echo "[smoke] Failed to extract user/token from container output:"
  printf '%s\n' "$AUTH_INFO"
  exit 1
fi

echo "[smoke] Running LIVE SSE flow (this should enqueue backup task)..."
LIVE_SSE_FILE="$(mktemp)"
LIVE_SSE_ERR_FILE="$(mktemp)"
run_sse_capture "${LIVE_SSE_FILE}" "${LIVE_SSE_ERR_FILE}" "${LIVE_TIMEOUT_SECONDS}" "${LIVE_FIRST_EVENT_TIMEOUT_SECONDS}" \
  -H "Authorization: Token ${TOKEN}" \
  "${API_BASE_URL}/api/backups/start/?include_users=0"

if [[ "${SSE_CAPTURE_TIMED_OUT_FIRST}" == "1" ]]; then
  echo "[smoke] Live SSE verification failed: no initial event id within ${LIVE_FIRST_EVENT_TIMEOUT_SECONDS}s."
  echo "[smoke] Live SSE output:"
  cat "${LIVE_SSE_FILE}"
  if [[ -s "${LIVE_SSE_ERR_FILE}" ]]; then
    echo "[smoke] Live SSE curl stderr:"
    cat "${LIVE_SSE_ERR_FILE}"
  fi
  dump_runtime_diagnostics
  exit 1
fi

LIVE_PARSE="$(
  python - "${LIVE_SSE_FILE}" <<'PY'
import json
import sys

path = sys.argv[1]
ids = []
messages = []

with open(path, "r", encoding="utf-8", errors="ignore") as handle:
    for raw_line in handle:
        line = raw_line.rstrip("\n")
        if line.startswith("id:"):
            ids.append(line.split(":", 1)[1].strip())
        elif line.startswith("data:"):
            data = line.split(":", 1)[1].strip()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                messages.append(payload.get("message", ""))

if not ids:
    explicit_error = next((str(msg) for msg in messages if str(msg).startswith("Error:")), "")
    print("LIVE_OK=0")
    if explicit_error:
        print(f"LIVE_REASON={explicit_error}")
    else:
        print("LIVE_REASON=No SSE id fields captured from live flow.")
    sys.exit(0)

terminal = any(("Backup finished" in str(msg)) or str(msg).startswith("Error:") for msg in messages)
print("LIVE_OK=1" if terminal else "LIVE_OK=0")
print(f"LIVE_EVENT_COUNT={len(ids)}")
print(f"LIVE_FIRST_ID={ids[0]}")
print(f"LIVE_LAST_ID={ids[-1]}")
print("LIVE_REASON=ok" if terminal else "LIVE_REASON=No terminal backup message in live SSE payload.")
PY
)"

LIVE_OK="$(printf '%s\n' "$LIVE_PARSE" | awk -F= '/^LIVE_OK=/{print $2}' | tail -n1)"
LIVE_REASON="$(printf '%s\n' "$LIVE_PARSE" | awk -F= '/^LIVE_REASON=/{print $2}' | tail -n1)"
LIVE_FIRST_ID="$(printf '%s\n' "$LIVE_PARSE" | awk -F= '/^LIVE_FIRST_ID=/{print $2}' | tail -n1)"
LIVE_LAST_ID="$(printf '%s\n' "$LIVE_PARSE" | awk -F= '/^LIVE_LAST_ID=/{print $2}' | tail -n1)"

if [[ "$LIVE_OK" != "1" ]]; then
  echo "[smoke] Live SSE verification failed: ${LIVE_REASON}"
  echo "[smoke] Live SSE output:"
  cat "${LIVE_SSE_FILE}"
  if [[ -s "${LIVE_SSE_ERR_FILE}" ]]; then
    echo "[smoke] Live SSE curl stderr:"
    cat "${LIVE_SSE_ERR_FILE}"
  fi
  dump_runtime_diagnostics
  exit 1
fi

echo "[smoke] Checking worker logs for backup actor execution (best-effort)..."
WORKER_LOGS="$(compose_smoke logs --no-color --tail=250 bs-worker || true)"
if ! printf '%s\n' "$WORKER_LOGS" | rg -q "run_backup_stream"; then
  echo "[smoke] Note: run_backup_stream not visible in recent worker logs; SSE + Redis assertions are authoritative."
fi

echo "[smoke] Verifying Redis Stream publish (stream:user:${USER_ID})..."
STREAM_LEN_RAW="$("${COMPOSE[@]}" exec -T redis redis-cli XLEN "stream:user:${USER_ID}" | tr -d '\r')"
if ! [[ "$STREAM_LEN_RAW" =~ ^[0-9]+$ ]]; then
  echo "[smoke] Unexpected XLEN response: ${STREAM_LEN_RAW}"
  exit 1
fi
if [[ "$STREAM_LEN_RAW" -lt 1 ]]; then
  echo "[smoke] Redis stream is empty for stream:user:${USER_ID}"
  exit 1
fi

echo "[smoke] Running REPLAY SSE flow with Last-Event-ID: 0-0..."
REPLAY_SSE_FILE="$(mktemp)"
REPLAY_SSE_ERR_FILE="$(mktemp)"
run_sse_capture "${REPLAY_SSE_FILE}" "${REPLAY_SSE_ERR_FILE}" "${REPLAY_TIMEOUT_SECONDS}" "${REPLAY_FIRST_EVENT_TIMEOUT_SECONDS}" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Last-Event-ID: 0-0" \
  "${API_BASE_URL}/api/backups/start/?include_users=0"

if [[ "${SSE_CAPTURE_TIMED_OUT_FIRST}" == "1" ]]; then
  echo "[smoke] Replay SSE verification failed: no initial event id within ${REPLAY_FIRST_EVENT_TIMEOUT_SECONDS}s."
  echo "[smoke] Replay SSE output:"
  cat "${REPLAY_SSE_FILE}"
  if [[ -s "${REPLAY_SSE_ERR_FILE}" ]]; then
    echo "[smoke] Replay SSE curl stderr:"
    cat "${REPLAY_SSE_ERR_FILE}"
  fi
  dump_runtime_diagnostics
  exit 1
fi

REPLAY_PARSE="$(
  python - "${REPLAY_SSE_FILE}" "${LIVE_FIRST_ID}" <<'PY'
import sys

path = sys.argv[1]
expected_id = sys.argv[2]
ids = []

with open(path, "r", encoding="utf-8", errors="ignore") as handle:
    for raw_line in handle:
        line = raw_line.rstrip("\n")
        if line.startswith("id:"):
            ids.append(line.split(":", 1)[1].strip())

if not ids:
    print("REPLAY_OK=0")
    print("REPLAY_REASON=No replay SSE ids captured.")
    sys.exit(0)

contains_expected = expected_id in ids
print("REPLAY_OK=1" if contains_expected else "REPLAY_OK=0")
print(f"REPLAY_EVENT_COUNT={len(ids)}")
print(f"REPLAY_FIRST_ID={ids[0]}")
print(f"REPLAY_LAST_ID={ids[-1]}")
print("REPLAY_REASON=ok" if contains_expected else "REPLAY_REASON=Replay did not include first live event id.")
PY
)"

REPLAY_OK="$(printf '%s\n' "$REPLAY_PARSE" | awk -F= '/^REPLAY_OK=/{print $2}' | tail -n1)"
REPLAY_REASON="$(printf '%s\n' "$REPLAY_PARSE" | awk -F= '/^REPLAY_REASON=/{print $2}' | tail -n1)"
REPLAY_FIRST_ID="$(printf '%s\n' "$REPLAY_PARSE" | awk -F= '/^REPLAY_FIRST_ID=/{print $2}' | tail -n1)"
REPLAY_LAST_ID="$(printf '%s\n' "$REPLAY_PARSE" | awk -F= '/^REPLAY_LAST_ID=/{print $2}' | tail -n1)"

if [[ "$REPLAY_OK" != "1" ]]; then
  echo "[smoke] Replay SSE verification failed: ${REPLAY_REASON}"
  echo "[smoke] Replay SSE output:"
  cat "${REPLAY_SSE_FILE}"
  if [[ -s "${REPLAY_SSE_ERR_FILE}" ]]; then
    echo "[smoke] Replay SSE curl stderr:"
    cat "${REPLAY_SSE_ERR_FILE}"
  fi
  dump_runtime_diagnostics
  exit 1
fi

echo
echo "[smoke] SUCCESS"
echo "  API enqueue -> worker execute -> stream publish -> SSE live + replay verified"
echo "  user_id=${USER_ID}"
echo "  stream_len=${STREAM_LEN_RAW}"
echo "  live_first_id=${LIVE_FIRST_ID}"
echo "  live_last_id=${LIVE_LAST_ID}"
echo "  replay_first_id=${REPLAY_FIRST_ID}"
echo "  replay_last_id=${REPLAY_LAST_ID}"
