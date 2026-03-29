"""
FILE_ROLE: Provides cache-backend resilience helpers for API throttles and views.

KEY_COMPONENTS:
- is_transient_cache_backend_error: Module symbol.

INTERACTIONS:
- Depends on: nearby API/core services and DRF helpers used in this module.

AI_GUIDELINES:
- Keep this module focused on reusable API infrastructure rather than domain orchestration.
- Preserve the existing contract so split view modules can import these helpers safely.
"""

from __future__ import annotations


def is_transient_cache_backend_error(exc: BaseException | None) -> bool:
    """Return True when the exception chain points to a transient Redis/cache outage."""
    if exc is None:
        return False

    try:
        from django_redis.exceptions import ConnectionInterrupted
    except Exception:  # pragma: no cover - optional dependency import guard
        ConnectionInterrupted = ()

    try:
        from redis.exceptions import BusyLoadingError
        from redis.exceptions import ConnectionError as RedisConnectionError
        from redis.exceptions import RedisError, TimeoutError
    except Exception:  # pragma: no cover - optional dependency import guard
        BusyLoadingError = ()
        RedisConnectionError = ()
        RedisError = ()
        TimeoutError = ()

    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(
            current, (ConnectionInterrupted, BusyLoadingError, RedisConnectionError, TimeoutError, RedisError)
        ):
            return True

        message = str(current).lower()
        if any(
            fragment in message
            for fragment in (
                "redis is loading the dataset in memory",
                "busyloadingerror",
                "redis unavailable",
                "error connecting to redis",
                "connection interrupted",
            )
        ):
            return True

        current = current.__cause__ or current.__context__

    return False
