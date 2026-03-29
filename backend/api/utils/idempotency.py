"""Idempotency helpers for replay-safe API requests and cached responses."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from api.utils.contracts import get_request_id
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import UploadedFile

logger = logging.getLogger(__name__)

IDEMPOTENCY_CACHE_PREFIX = "async-idempotency"
IDEMPOTENCY_FIELD_NAMES = {"idempotency_key", "idempotencyKey"}


class IdempotencyConflictError(ValueError):
    """Raised when the same idempotency key is reused with a different payload."""


def _ttl_seconds() -> int:
    return int(getattr(settings, "ASYNC_JOB_IDEMPOTENCY_TTL_SECONDS", 24 * 60 * 60) or (24 * 60 * 60))


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


def _is_file_like(value: Any) -> bool:
    return isinstance(value, UploadedFile) or (
        hasattr(value, "name") and hasattr(value, "size") and (hasattr(value, "chunks") or hasattr(value, "read"))
    )


def _normalize_idempotency_value(value: Any) -> Any:
    if value is None:
        return None

    if hasattr(value, "lists") and callable(getattr(value, "lists")):
        normalized: dict[str, Any] = {}
        for key, values in sorted(value.lists(), key=lambda item: str(item[0])):
            key_text = str(key)
            if key_text in IDEMPOTENCY_FIELD_NAMES:
                continue
            normalized[key_text] = _normalize_idempotency_value(values if len(values) != 1 else values[0])
        return normalized

    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda item: str(item[0])):
            key_text = str(key)
            if key_text in IDEMPOTENCY_FIELD_NAMES:
                continue
            normalized[key_text] = _normalize_idempotency_value(item)
        return normalized

    if _is_file_like(value):
        file_metadata = {
            "__file__": True,
            "name": normalize_idempotency_key(getattr(value, "name", None)),
            "size": int(getattr(value, "size", 0) or 0),
            "content_type": normalize_idempotency_key(getattr(value, "content_type", None)),
        }
        if getattr(value, "content_type_extra", None):
            file_metadata["content_type_extra"] = _normalize_idempotency_value(getattr(value, "content_type_extra"))
        return file_metadata

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, (list, tuple)):
        return [_normalize_idempotency_value(item) for item in value]

    if isinstance(value, set):
        return sorted(
            (_normalize_idempotency_value(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True)
        )

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def build_request_idempotency_fingerprint(request: Any | None = None) -> str | None:
    if request is None:
        return None

    payload: dict[str, Any] = {}

    query_params = getattr(request, "query_params", None)
    if query_params is not None:
        payload["query"] = _normalize_idempotency_value(query_params)

    data = getattr(request, "data", None)
    if data is not None:
        payload["data"] = _normalize_idempotency_value(data)

    files = getattr(request, "FILES", None)
    if files is not None:
        payload["files"] = _normalize_idempotency_value(files)

    if not payload:
        return None

    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_async_idempotency_cache_key(*, namespace: str, user_id: Any, idempotency_key: str) -> str:
    digest_source = f"{namespace}:{user_id}:{idempotency_key}".encode("utf-8")
    digest = hashlib.sha256(digest_source).hexdigest()
    return f"{IDEMPOTENCY_CACHE_PREFIX}:{namespace}:{user_id}:{digest}"


def _coerce_cached_record(cached: Any) -> dict[str, Any] | None:
    if cached is None:
        return None
    if isinstance(cached, str):
        text = cached.strip()
        if not text:
            return None
        return {"job_id": text}
    if isinstance(cached, Mapping):
        return dict(cached)

    text = normalize_idempotency_key(cached)
    if not text:
        return None
    return {"job_id": text}


def _build_record(*, kind: str, fingerprint: str | None = None, job_id: Any | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {"kind": kind}
    if fingerprint:
        record["fingerprint"] = fingerprint
    if job_id is not None:
        record["job_id"] = str(job_id)
    return record


def _record_fingerprint_mismatch(
    *, namespace: str, user_id: Any, cache_key: str, expected: str | None, actual: str | None
) -> None:
    logger.warning(
        "Async idempotency conflict namespace=%s user_id=%s cache_key=%s expected_fingerprint=%s actual_fingerprint=%s",
        namespace,
        user_id,
        cache_key,
        expected,
        actual,
    )
    raise IdempotencyConflictError("The same idempotency key was reused with a different request payload.")


def store_async_job_idempotency(cache_key: str, job_id: Any, *, fingerprint: str | None = None) -> None:
    cache.set(cache_key, _build_record(kind="job", fingerprint=fingerprint, job_id=job_id), timeout=_ttl_seconds())


def get_cached_async_job_id(cache_key: str) -> str | None:
    cached = _coerce_cached_record(cache.get(cache_key))
    if cached is None:
        return None
    text = normalize_idempotency_key(cached.get("job_id"))
    return text


def resolve_cached_async_job(
    *, cache_key: str, queryset, fingerprint: str | None = None, namespace: str | None = None, user_id: Any = None
):
    cached = _coerce_cached_record(cache.get(cache_key))
    if cached is None:
        return None

    cached_fingerprint = normalize_idempotency_key(cached.get("fingerprint"))
    if fingerprint and cached_fingerprint and cached_fingerprint != fingerprint:
        _record_fingerprint_mismatch(
            namespace=namespace or "unknown",
            user_id=user_id,
            cache_key=cache_key,
            expected=cached_fingerprint,
            actual=fingerprint,
        )

    job_id = normalize_idempotency_key(cached.get("job_id"))
    if not job_id:
        return None

    job = queryset.filter(id=job_id).first()
    if job is not None:
        return job

    cache.delete(cache_key)
    return None


def resolve_request_idempotent_job(
    *, request: Any | None = None, namespace: str, user_id: Any, queryset, fingerprint: str | None = None
):
    idempotency_key = get_request_idempotency_key(request)
    if not idempotency_key:
        return None, None

    fingerprint = fingerprint or build_request_idempotency_fingerprint(request)
    cache_key = build_async_idempotency_cache_key(
        namespace=namespace,
        user_id=user_id,
        idempotency_key=idempotency_key,
    )
    cached_job = resolve_cached_async_job(
        cache_key=cache_key,
        queryset=queryset,
        fingerprint=fingerprint,
        namespace=namespace,
        user_id=user_id,
    )
    if cached_job is not None:
        logger.info(
            "Async job idempotency hit namespace=%s user_id=%s job_id=%s request_id=%s",
            namespace,
            user_id,
            getattr(cached_job, "id", None),
            get_request_id(request),
        )
    return cache_key, cached_job


def store_request_idempotent_job(*, cache_key: str | None, job_id: Any, fingerprint: str | None = None) -> None:
    if not cache_key:
        return
    store_async_job_idempotency(cache_key, job_id, fingerprint=fingerprint)


def claim_request_idempotency(
    *,
    request: Any | None = None,
    namespace: str,
    user_id: Any,
    fingerprint: str | None = None,
) -> tuple[str | None, bool]:
    idempotency_key = get_request_idempotency_key(request)
    if not idempotency_key:
        return None, False

    fingerprint = fingerprint or build_request_idempotency_fingerprint(request)
    cache_key = build_async_idempotency_cache_key(
        namespace=namespace,
        user_id=user_id,
        idempotency_key=idempotency_key,
    )
    cached = _coerce_cached_record(cache.get(cache_key))
    if cached is not None:
        cached_fingerprint = normalize_idempotency_key(cached.get("fingerprint"))
        if fingerprint and cached_fingerprint and cached_fingerprint != fingerprint:
            _record_fingerprint_mismatch(
                namespace=namespace,
                user_id=user_id,
                cache_key=cache_key,
                expected=cached_fingerprint,
                actual=fingerprint,
            )
        logger.info(
            "Async request idempotency hit namespace=%s user_id=%s request_id=%s cache_key=%s",
            namespace,
            user_id,
            get_request_id(request),
            cache_key,
        )
        return cache_key, True

    record = _build_record(kind="claim", fingerprint=fingerprint)
    try:
        added = cache.add(cache_key, record, timeout=_ttl_seconds())
    except Exception as exc:
        logger.warning("Async idempotency claim skipped due to cache backend error: %s", exc)
        return cache_key, False

    if added:
        return cache_key, False

    cached = _coerce_cached_record(cache.get(cache_key))
    if cached is not None:
        cached_fingerprint = normalize_idempotency_key(cached.get("fingerprint"))
        if fingerprint and cached_fingerprint and cached_fingerprint != fingerprint:
            _record_fingerprint_mismatch(
                namespace=namespace,
                user_id=user_id,
                cache_key=cache_key,
                expected=cached_fingerprint,
                actual=fingerprint,
            )
    return cache_key, True
