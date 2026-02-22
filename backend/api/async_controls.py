from __future__ import annotations

import uuid

from django.conf import settings
from django.core.cache import cache

ASYNC_GUARD_COUNTER_PREFIX = "observability:async_guard"


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


def observability_counter_ttl_seconds() -> int:
    configured = getattr(settings, "ASYNC_GUARD_OBSERVABILITY_TTL_SECONDS", 7 * 24 * 60 * 60)
    return _coerce_positive_int(configured, 7 * 24 * 60 * 60)


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


def build_guard_counter_key(*, namespace: str, event: str) -> str:
    return f"{ASYNC_GUARD_COUNTER_PREFIX}:{namespace}:{event}"


def increment_guard_counter(*, namespace: str, event: str) -> int:
    key = build_guard_counter_key(namespace=namespace, event=event)
    ttl = observability_counter_ttl_seconds()
    try:
        return int(cache.incr(key))
    except ValueError:
        cache.set(key, 1, timeout=max(1, ttl))
        return 1
