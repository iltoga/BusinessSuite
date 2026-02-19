from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.utils import timezone

RECENT_WORKFLOW_NOTIFICATION_WINDOW_HOURS = 24
RECENT_WORKFLOW_NOTIFICATION_WINDOW = timedelta(hours=RECENT_WORKFLOW_NOTIFICATION_WINDOW_HOURS)

WORKFLOW_NOTIFICATION_STREAM_CURSOR_CACHE_KEY = "workflow_notifications:stream:cursor"
WORKFLOW_NOTIFICATION_STREAM_LAST_EVENT_CACHE_KEY = "workflow_notifications:stream:last_event"
WORKFLOW_NOTIFICATION_STREAM_CACHE_TIMEOUT_SECONDS = 60 * 60 * 48


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def is_recent_workflow_notification(notification: Any, *, now=None) -> bool:
    created_at = getattr(notification, "created_at", None)
    if created_at is None:
        return False
    current_time = now or timezone.now()
    return created_at >= current_time - RECENT_WORKFLOW_NOTIFICATION_WINDOW


def get_workflow_notification_stream_cursor() -> int:
    return _coerce_int(cache.get(WORKFLOW_NOTIFICATION_STREAM_CURSOR_CACHE_KEY), default=0)


def get_workflow_notification_stream_last_event() -> dict[str, Any] | None:
    payload = cache.get(WORKFLOW_NOTIFICATION_STREAM_LAST_EVENT_CACHE_KEY)
    if isinstance(payload, dict):
        return payload
    return None


def bump_workflow_notification_stream_cursor(*, notification_id: int | None, operation: str) -> int:
    cache.add(
        WORKFLOW_NOTIFICATION_STREAM_CURSOR_CACHE_KEY,
        0,
        timeout=WORKFLOW_NOTIFICATION_STREAM_CACHE_TIMEOUT_SECONDS,
    )
    try:
        cursor = _coerce_int(cache.incr(WORKFLOW_NOTIFICATION_STREAM_CURSOR_CACHE_KEY), default=0)
    except Exception:
        cursor = get_workflow_notification_stream_cursor() + 1
        cache.set(
            WORKFLOW_NOTIFICATION_STREAM_CURSOR_CACHE_KEY,
            cursor,
            timeout=WORKFLOW_NOTIFICATION_STREAM_CACHE_TIMEOUT_SECONDS,
        )

    cache.set(
        WORKFLOW_NOTIFICATION_STREAM_LAST_EVENT_CACHE_KEY,
        {
            "cursor": cursor,
            "operation": operation,
            "notificationId": notification_id,
            "changedAt": timezone.now().isoformat(),
        },
        timeout=WORKFLOW_NOTIFICATION_STREAM_CACHE_TIMEOUT_SECONDS,
    )
    return cursor


def reset_workflow_notification_stream_state() -> None:
    cache.delete_many(
        [
            WORKFLOW_NOTIFICATION_STREAM_CURSOR_CACHE_KEY,
            WORKFLOW_NOTIFICATION_STREAM_LAST_EVENT_CACHE_KEY,
        ]
    )

