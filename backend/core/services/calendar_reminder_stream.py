from __future__ import annotations

from typing import Any

from django.core.cache import cache
from django.utils import timezone

CALENDAR_REMINDER_STREAM_CURSOR_CACHE_KEY = "calendar_reminders:stream:cursor"
CALENDAR_REMINDER_STREAM_LAST_EVENT_CACHE_KEY = "calendar_reminders:stream:last_event"
CALENDAR_REMINDER_STREAM_CACHE_TIMEOUT_SECONDS = 60 * 60 * 48


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_calendar_reminder_stream_cursor() -> int:
    return _coerce_int(cache.get(CALENDAR_REMINDER_STREAM_CURSOR_CACHE_KEY), default=0)


def get_calendar_reminder_stream_last_event() -> dict[str, Any] | None:
    payload = cache.get(CALENDAR_REMINDER_STREAM_LAST_EVENT_CACHE_KEY)
    if isinstance(payload, dict):
        return payload
    return None


def bump_calendar_reminder_stream_cursor(
    *,
    reminder_id: int | None,
    operation: str,
    owner_id: int | None,
) -> int:
    cache.add(
        CALENDAR_REMINDER_STREAM_CURSOR_CACHE_KEY,
        0,
        timeout=CALENDAR_REMINDER_STREAM_CACHE_TIMEOUT_SECONDS,
    )
    try:
        cursor = _coerce_int(cache.incr(CALENDAR_REMINDER_STREAM_CURSOR_CACHE_KEY), default=0)
    except Exception:
        cursor = get_calendar_reminder_stream_cursor() + 1
        cache.set(
            CALENDAR_REMINDER_STREAM_CURSOR_CACHE_KEY,
            cursor,
            timeout=CALENDAR_REMINDER_STREAM_CACHE_TIMEOUT_SECONDS,
        )

    cache.set(
        CALENDAR_REMINDER_STREAM_LAST_EVENT_CACHE_KEY,
        {
            "cursor": cursor,
            "operation": operation,
            "reminderId": reminder_id,
            "ownerId": owner_id,
            "changedAt": timezone.now().isoformat(),
        },
        timeout=CALENDAR_REMINDER_STREAM_CACHE_TIMEOUT_SECONDS,
    )
    return cursor


def reset_calendar_reminder_stream_state() -> None:
    cache.delete_many(
        [
            CALENDAR_REMINDER_STREAM_CURSOR_CACHE_KEY,
            CALENDAR_REMINDER_STREAM_LAST_EVENT_CACHE_KEY,
        ]
    )
