from __future__ import annotations

import os
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

import redis
from django.conf import settings

if TYPE_CHECKING:
    # `redis.asyncio` is not exported in redis' __all__, so type checkers will
    # complain if imported unconditionally. Keep it under TYPE_CHECKING for
    # static typing only.
    from redis.asyncio import Redis as AsyncRedis

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _replace_db(redis_url: str, db: int) -> str:
    parsed = urlparse(redis_url)
    return str(urlunparse(parsed._replace(path=f"/{int(db)}")))


def _setting_or_env(name: str, default: str = "") -> str:
    value = getattr(settings, name, None)
    if value is None:
        return str(os.getenv(name, default))
    text = str(value).strip()
    if text:
        return text
    return str(os.getenv(name, default))


def _running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _normalize_host(host: str, *, docker_default: str = "bs-redis") -> str:
    text = str(host or "").strip()
    if _running_in_docker() and text in _LOOPBACK_HOSTS:
        return docker_default
    return text


def _normalize_redis_url(redis_url: str) -> str:
    text = str(redis_url or "").strip()
    if not text:
        return text

    parsed = urlparse(text)
    host = parsed.hostname or ""
    normalized_host = _normalize_host(host)
    if not host or normalized_host == host:
        return text

    netloc = ""
    username = parsed.username
    if username is not None:
        netloc += str(username)
        password = parsed.password
        if password is not None:
            netloc += f":{password}"
        netloc += "@"
    netloc += normalized_host
    port = parsed.port
    if port is not None:
        netloc += f":{port}"

    return str(urlunparse(parsed._replace(netloc=netloc)))


def _build_redis_url() -> str:
    desired_db = int(getattr(settings, "DRAMATIQ_REDIS_DB", 0) or 0)

    # Prefer explicit Dramatiq URL when provided.
    dramatiq_redis_url = _normalize_redis_url(_setting_or_env("DRAMATIQ_REDIS_URL", ""))
    if dramatiq_redis_url:
        return _replace_db(dramatiq_redis_url, desired_db)

    # Preserve credentials/TLS/query params when REDIS_URL is configured.
    redis_url = _normalize_redis_url(_setting_or_env("REDIS_URL", ""))
    if redis_url:
        return _replace_db(redis_url, desired_db)

    # Fallback to host/port only when full URLs are not provided.
    raw_host = _setting_or_env("REDIS_HOST", "")
    host = _normalize_host(raw_host) if raw_host else ""
    port = int(_setting_or_env("REDIS_PORT", "6379") or 6379)
    if host:
        return f"redis://{host}:{port}/{desired_db}"

    fallback_host = _normalize_host("localhost")
    return f"redis://{fallback_host}:{port}/{desired_db}"


def build_redis_url(*, db: int | None = None) -> str:
    base_url = _build_redis_url()
    if db is None:
        return base_url

    return _replace_db(base_url, db)


def get_redis_client(
    *,
    db: int | None = None,
    decode_responses: bool = False,
    socket_timeout: float = 5,
    socket_connect_timeout: float = 5,
) -> redis.Redis:
    return redis.Redis.from_url(
        build_redis_url(db=db),
        decode_responses=decode_responses,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_connect_timeout,
        retry_on_timeout=True,
    )


def get_async_redis_client(
    *,
    db: int | None = None,
    decode_responses: bool = False,
    socket_timeout: float = 5,
    socket_connect_timeout: float = 5,
) -> "AsyncRedis":
    # `redis.asyncio` is not exported in redis' __all__, so type checkers may raise
    # `reportPrivateImportUsage`. We still import it at runtime for async support.
    import redis.asyncio as aioredis  # type: ignore[reportPrivateImportUsage]

    return aioredis.from_url(
        build_redis_url(db=db),
        decode_responses=decode_responses,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_connect_timeout,
        retry_on_timeout=True,
    )
