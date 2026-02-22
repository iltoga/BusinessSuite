from __future__ import annotations

import uuid

from django.conf import settings
from django.core.cache import cache

TASK_LOCK_PREFIX = "tasks:idempotency"


def _coerce_positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return default


def task_lock_ttl_seconds() -> int:
    configured = getattr(settings, "TASK_IDEMPOTENCY_LOCK_TTL_SECONDS", 60 * 60)
    return _coerce_positive_int(configured, 60 * 60)


def build_task_lock_key(*, namespace: str, item_id: str) -> str:
    return f"{TASK_LOCK_PREFIX}:{namespace}:{item_id}"


def acquire_task_lock(lock_key: str, ttl_seconds: int | None = None) -> str | None:
    ttl = task_lock_ttl_seconds() if ttl_seconds is None else _coerce_positive_int(ttl_seconds, task_lock_ttl_seconds())
    token = uuid.uuid4().hex
    acquired = cache.add(lock_key, token, timeout=max(1, ttl))
    return token if acquired else None


def release_task_lock(lock_key: str, token: str) -> None:
    if cache.get(lock_key) == token:
        cache.delete(lock_key)
