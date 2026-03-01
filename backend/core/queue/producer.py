from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Mapping

from core.queue.payloads import encode_payload
from core.services.logger_service import Logger
from django.conf import settings

logger = Logger.get_logger(__name__)


def _database_connect_kwargs() -> dict[str, Any]:
    database = settings.DATABASES.get("default", {})
    return {
        "dbname": database.get("NAME") or "",
        "user": database.get("USER") or "",
        "password": database.get("PASSWORD") or "",
        "host": database.get("HOST") or "",
        "port": database.get("PORT") or "",
    }


def _fallback_local(
    *,
    entrypoint: str,
    payload: dict[str, Any],
    run_local: Callable[..., Any] | None,
    reason: str,
) -> str | None:
    if run_local is None:
        raise RuntimeError(reason)

    logger.warning(
        "Queue fallback to local execution for entrypoint=%s reason=%s",
        entrypoint,
        reason,
    )
    run_local(**payload)
    return None


def enqueue_job(
    *,
    entrypoint: str,
    payload: Mapping[str, Any] | None = None,
    priority: int = 0,
    delay_seconds: int | float | None = None,
    dedupe_key: str | None = None,
    headers: Mapping[str, str] | None = None,
    run_local: Callable[..., Any] | None = None,
) -> str | None:
    normalized_payload = dict(payload or {})

    if getattr(settings, "TESTING", False):
        return _fallback_local(
            entrypoint=entrypoint,
            payload=normalized_payload,
            run_local=run_local,
            reason="testing_mode",
        )

    try:
        import psycopg
        from pgqueuer import errors as pgq_errors
        from pgqueuer.db import SyncPsycopgDriver
        from pgqueuer.queries import SyncQueries
    except Exception as exc:
        return _fallback_local(
            entrypoint=entrypoint,
            payload=normalized_payload,
            run_local=run_local,
            reason=f"missing_pgqueue_driver:{type(exc).__name__}",
        )

    execute_after = None
    if delay_seconds is not None:
        delay = max(0.0, float(delay_seconds))
        execute_after = timedelta(seconds=delay)

    encoded_payload = encode_payload(normalized_payload)
    normalized_headers = dict(headers) if headers is not None else None

    with psycopg.connect(**_database_connect_kwargs(), autocommit=True) as connection:
        queries = SyncQueries(SyncPsycopgDriver(connection))
        try:
            job_ids = queries.enqueue(
                entrypoint=entrypoint,
                payload=encoded_payload,
                priority=int(priority),
                execute_after=execute_after,
                dedupe_key=dedupe_key,
                headers=normalized_headers,
            )
        except pgq_errors.DuplicateJobError:
            logger.info(
                "Skipped duplicate queue job for entrypoint=%s dedupe_key=%s",
                entrypoint,
                dedupe_key,
            )
            return None

    return str(job_ids[0]) if job_ids else None
