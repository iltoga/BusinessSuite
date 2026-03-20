from __future__ import annotations

import hashlib
from typing import Any

from django.conf import settings
from django.core.cache import cache

IDEMPOTENCY_CACHE_PREFIX = "async-idempotency"


def normalize_idempotency_key(value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
