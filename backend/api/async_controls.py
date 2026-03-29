"""
FILE_ROLE: Provides async enqueue guard helpers for API views.

KEY_COMPONENTS:
- _coerce_positive_int: Module symbol.
- enqueue_guard_ttl_seconds: Module symbol.
- observability_counter_ttl_seconds: Module symbol.
- build_user_enqueue_guard_key: Module symbol.
- acquire_enqueue_guard: Module symbol.
- release_enqueue_guard: Module symbol.
- build_guard_counter_key: Module symbol.
- increment_guard_counter: Module symbol.

INTERACTIONS:
- Depends on: nearby API/core services and DRF helpers used in this module.

AI_GUIDELINES:
- Keep this module focused on reusable API infrastructure rather than domain orchestration.
- Preserve the existing contract so split view modules can import these helpers safely.
"""

from __future__ import annotations

import logging
import uuid

from api.cache_resilience import is_transient_cache_backend_error
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

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
    try:
        acquired = cache.add(lock_key, token, timeout=max(1, ttl))
    except Exception as exc:
        if not is_transient_cache_backend_error(exc):
            raise

        logger.warning("Async enqueue guard bypassed because the cache backend is temporarily unavailable: %s", exc)
        return f"cache-bypass:{token}"
    return token if acquired else None


def release_enqueue_guard(lock_key: str, token: str) -> None:
    if token.startswith("cache-bypass:"):
        return

    try:
        if cache.get(lock_key) == token:
            cache.delete(lock_key)
    except Exception as exc:
        if not is_transient_cache_backend_error(exc):
            raise

        logger.warning(
            "Async enqueue guard release skipped because the cache backend is temporarily unavailable: %s", exc
        )


def build_guard_counter_key(*, namespace: str, event: str) -> str:
    return f"{ASYNC_GUARD_COUNTER_PREFIX}:{namespace}:{event}"


def increment_guard_counter(*, namespace: str, event: str) -> int:
    key = build_guard_counter_key(namespace=namespace, event=event)
    ttl = observability_counter_ttl_seconds()
    try:
        return int(cache.incr(key))
    except ValueError:
        try:
            cache.set(key, 1, timeout=max(1, ttl))
        except Exception as exc:
            if not is_transient_cache_backend_error(exc):
                raise

            logger.warning(
                "Async guard counter initialization skipped because the cache backend is temporarily unavailable: %s",
                exc,
            )
            return 0
        return 1
    except Exception as exc:
        if not is_transient_cache_backend_error(exc):
            raise

        logger.warning(
            "Async guard observability increment skipped because the cache backend is temporarily unavailable: %s", exc
        )
        return 0
