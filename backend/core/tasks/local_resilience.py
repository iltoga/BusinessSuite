from __future__ import annotations

import logging

import requests
from core.models.local_resilience import LocalResilienceSettings, SyncChangeLog, SyncCursor
from core.queue import enqueue_job
from core.services.sync_service import get_local_node_id, ingest_remote_changes
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

ENTRYPOINT_PUSH_LOCAL_CHANGES_TASK = "core.push_local_changes"
ENTRYPOINT_PULL_REMOTE_CHANGES_TASK = "core.pull_remote_changes"


def _sync_enabled(*, allow_pull_when_disabled: bool = False) -> bool:
    if not bool(getattr(settings, "LOCAL_SYNC_ENABLED", False)):
        return False

    if allow_pull_when_disabled:
        return True

    try:
        return bool(LocalResilienceSettings.get_solo().enabled)
    except Exception:
        return False


def _remote_base_url() -> str:
    return str(getattr(settings, "LOCAL_SYNC_REMOTE_BASE_URL", "") or "").strip().rstrip("/")


def _request_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = str(getattr(settings, "LOCAL_SYNC_REMOTE_TOKEN", "") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _cursor() -> SyncCursor:
    cursor, _ = SyncCursor.objects.get_or_create(node_id="remote")
    return cursor


def _push_once(*, limit: int) -> dict[str, int]:
    if not _sync_enabled(allow_pull_when_disabled=False):
        return {"pushed": 0, "skipped": 0}

    base_url = _remote_base_url()
    if not base_url:
        return {"pushed": 0, "skipped": 0}

    cursor = _cursor()
    local_node_id = get_local_node_id()
    queryset = (
        SyncChangeLog.objects.filter(source_node=local_node_id, seq__gt=cursor.last_pushed_seq)
        .order_by("seq")[: max(1, int(limit))]
    )
    rows = list(queryset)
    if not rows:
        return {"pushed": 0, "skipped": 0}

    changes = [
        {
            "seq": int(row.seq),
            "source_node": row.source_node,
            "model_label": row.model_label,
            "object_pk": row.object_pk,
            "operation": row.operation,
            "payload": row.payload,
            "source_timestamp": row.source_timestamp.isoformat(),
            "checksum": row.checksum,
        }
        for row in rows
    ]

    timeout = float(getattr(settings, "LOCAL_SYNC_REQUEST_TIMEOUT_SECONDS", 10))
    response = requests.post(
        f"{base_url}/api/sync/changes/push/",
        json={"source_node": local_node_id, "changes": changes},
        headers=_request_headers(),
        timeout=timeout,
    )
    response.raise_for_status()

    max_seq = max(int(row.seq) for row in rows)
    cursor.last_pushed_seq = max_seq
    cursor.last_pushed_at = timezone.now()
    cursor.last_error = ""
    cursor.save(update_fields=["last_pushed_seq", "last_pushed_at", "last_error", "updated_at"])

    return {"pushed": len(rows), "skipped": 0}


def _pull_once(*, limit: int) -> dict[str, int]:
    # Pull remains enabled whenever LOCAL_SYNC_ENABLED is true so a node can
    # receive global toggles and bootstrap settings from remote.
    if not _sync_enabled(allow_pull_when_disabled=True):
        return {"accepted": 0, "conflicts": 0, "skipped": 0}

    base_url = _remote_base_url()
    if not base_url:
        return {"accepted": 0, "conflicts": 0, "skipped": 0}

    cursor = _cursor()
    timeout = float(getattr(settings, "LOCAL_SYNC_REQUEST_TIMEOUT_SECONDS", 10))
    response = requests.get(
        f"{base_url}/api/sync/changes/pull/",
        params={"after_seq": int(cursor.last_pulled_seq), "limit": int(limit)},
        headers=_request_headers(),
        timeout=timeout,
    )
    response.raise_for_status()

    payload = response.json() if response.content else {}
    changes = payload.get("changes") if isinstance(payload, dict) else []
    if not isinstance(changes, list) or not changes:
        return {"accepted": 0, "conflicts": 0, "skipped": 0}

    result = ingest_remote_changes(source_node="remote", changes=changes)
    max_remote_seq = max(int(item.get("seq") or 0) for item in changes if isinstance(item, dict))
    if max_remote_seq > cursor.last_pulled_seq:
        cursor.last_pulled_seq = max_remote_seq
    cursor.last_pulled_at = timezone.now()
    cursor.last_error = ""
    cursor.save(update_fields=["last_pulled_seq", "last_pulled_at", "last_error", "updated_at"])

    return {
        "accepted": int(result.get("accepted") or 0),
        "conflicts": int(result.get("conflicts") or 0),
        "skipped": int(result.get("skipped") or 0),
    }


def push_local_changes_task(*, limit: int | None = None) -> dict[str, int]:
    effective_limit = int(limit if limit is not None else getattr(settings, "LOCAL_SYNC_PUSH_LIMIT", 200))
    try:
        result = _push_once(limit=effective_limit)
        logger.info("Local sync push completed: %s", result)
        return result
    except Exception as exc:
        cursor = _cursor()
        cursor.last_error = f"push:{type(exc).__name__}:{exc}"
        cursor.save(update_fields=["last_error", "updated_at"])
        logger.warning("Local sync push failed: %s", exc)
        return {"pushed": 0, "skipped": 0}


def pull_remote_changes_task(*, limit: int | None = None) -> dict[str, int]:
    effective_limit = int(limit if limit is not None else getattr(settings, "LOCAL_SYNC_PULL_LIMIT", 200))
    try:
        result = _pull_once(limit=effective_limit)
        logger.info("Local sync pull completed: %s", result)
        return result
    except Exception as exc:
        cursor = _cursor()
        cursor.last_error = f"pull:{type(exc).__name__}:{exc}"
        cursor.save(update_fields=["last_error", "updated_at"])
        logger.warning("Local sync pull failed: %s", exc)
        return {"accepted": 0, "conflicts": 0, "skipped": 0}


def enqueue_push_local_changes_task(*, limit: int | None = None) -> str | None:
    return enqueue_job(
        entrypoint=ENTRYPOINT_PUSH_LOCAL_CHANGES_TASK,
        payload={"limit": limit},
        run_local=push_local_changes_task,
    )


def enqueue_pull_remote_changes_task(*, limit: int | None = None) -> str | None:
    return enqueue_job(
        entrypoint=ENTRYPOINT_PULL_REMOTE_CHANGES_TASK,
        payload={"limit": limit},
        run_local=pull_remote_changes_task,
    )
