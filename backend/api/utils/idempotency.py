from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

IDEMPOTENCY_CACHE_PREFIX = "async-idempotency"


def normalize_idempotency_key(value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def get_request_idempotency_key(request: Any | None = None) -> str | None:
    if request is None:
        return None

    candidates: list[Any] = []

    if hasattr(request, "headers"):
        candidates.append(request.headers.get("Idempotency-Key"))
    if hasattr(request, "META"):
        candidates.append(request.META.get("HTTP_IDEMPOTENCY_KEY"))

    payload = getattr(request, "data", None)
    if payload is not None and hasattr(payload, "get"):
        candidates.append(payload.get("idempotency_key"))
        candidates.append(payload.get("idempotencyKey"))

    query_params = getattr(request, "query_params", None)
    if query_params is not None and hasattr(query_params, "get"):
        candidates.append(query_params.get("idempotency_key"))
        candidates.append(query_params.get("idempotencyKey"))

    for candidate in candidates:
        key = normalize_idempotency_key(candidate)
        if key:
            return key
    return None


def build_async_idempotency_cache_key(*, namespace: str, user_id: Any, idempotency_key: str) -> str:
    digest_source = f"{namespace}:{user_id}:{idempotency_key}".encode("utf-8")
    digest = hashlib.sha256(digest_source).hexdigest()
    return f"{IDEMPOTENCY_CACHE_PREFIX}:{namespace}:{user_id}:{digest}"


def _ttl_seconds() -> int:
    return int(getattr(settings, "ASYNC_JOB_IDEMPOTENCY_TTL_SECONDS", 24 * 60 * 60) or (24 * 60 * 60))


def store_async_job_idempotency(cache_key: str, job_id: Any) -> None:
    cache.set(cache_key, str(job_id), timeout=_ttl_seconds())


def get_cached_async_job_id(cache_key: str) -> str | None:
    cached = cache.get(cache_key)
    if cached is None:
        return None
    text = str(cached).strip()
    return text or None


def resolve_cached_async_job(*, cache_key: str, queryset):
    job_id = get_cached_async_job_id(cache_key)
    if not job_id:
        return None

    job = queryset.filter(id=job_id).first()
    if job is not None:
        return job

    cache.delete(cache_key)
    return None


def resolve_request_idempotent_job(*, request: Any | None = None, namespace: str, user_id: Any, queryset):
    idempotency_key = get_request_idempotency_key(request)
    if not idempotency_key:
        return None, None

    cache_key = build_async_idempotency_cache_key(
        namespace=namespace,
        user_id=user_id,
        idempotency_key=idempotency_key,
    )
    cached_job = resolve_cached_async_job(cache_key=cache_key, queryset=queryset)
    if cached_job is not None:
        logger.info(
            "Async job idempotency hit namespace=%s user_id=%s job_id=%s",
            namespace,
            user_id,
            getattr(cached_job, "id", None),
        )
    return cache_key, cached_job


def store_request_idempotent_job(*, cache_key: str | None, job_id: Any) -> None:
    if not cache_key:
        return
    store_async_job_idempotency(cache_key, job_id)
