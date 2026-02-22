from __future__ import annotations

import uuid

from django.conf import settings
from django.core.cache import cache


def _coerce_positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return default


def enqueue_guard_ttl_seconds() -> int:
    configured = getattr(settings, "ASYNC_ENQUEUE_GUARD_TTL_SECONDS", 15)
    return _coerce_positive_int(configured, 15)


def build_user_enqueue_guard_key(*, namespace: str, user_id: int | None, scope: str | None = None) -> str:
    parts = ["async", namespace, "enqueue_guard", f"user:{user_id or 'anon'}"]
    if scope:
        parts.append(scope)
    return ":".join(parts)


def acquire_enqueue_guard(lock_key: str, ttl_seconds: int | None = None) -> str | None:
    token = uuid.uuid4().hex
    ttl = enqueue_guard_ttl_seconds() if ttl_seconds is None else _coerce_positive_int(ttl_seconds, 15)
    acquired = cache.add(lock_key, token, timeout=max(1, ttl))
    return token if acquired else None


def release_enqueue_guard(lock_key: str, token: str) -> None:
    if cache.get(lock_key) == token:
        cache.delete(lock_key)
