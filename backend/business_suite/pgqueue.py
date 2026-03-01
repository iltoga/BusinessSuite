from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, Callable

from core.queue.payloads import QueuePayloadError, decode_payload
from core.services.logger_service import Logger
from core.telemetry.pgqueue_tracing import instrument_entrypoint

logger = Logger.get_logger(__name__)


def _parse_hhmm(value: str) -> tuple[int, int]:
    parts = str(value or "").split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format '{value}'. Expected HH:MM.")

    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time value '{value}'. Expected HH:MM in 24h format.")

    return hour, minute


def _fixed_retry_executor_factory(*, max_attempts: int, delay_seconds: float) -> Callable[[Any], Any]:
    from pgqueuer.executors import RetryWithBackoffEntrypointExecutor

    def _factory(parameters):
        return RetryWithBackoffEntrypointExecutor(
            parameters,
            max_attempts=max_attempts,
            initial_delay=float(delay_seconds),
            backoff_multiplier=1.0,
            max_delay=float(delay_seconds),
            jitter=lambda: 0.0,
        )

    return _factory


def _register_sync_entrypoint(
    *,
    pgq,
    entrypoint: str,
    fn: Callable[..., Any],
    retry_timer_seconds: float = 0,
    executor_factory: Callable[[Any], Any] | None = None,
) -> None:
    traced_fn = instrument_entrypoint(entrypoint, fn)

    def _execute(job) -> None:
        try:
            payload = decode_payload(job.payload)
        except QueuePayloadError:
            logger.exception("Invalid payload for entrypoint=%s", entrypoint)
            raise
        traced_fn(**payload)

    pgq.entrypoint(
        entrypoint,
        retry_timer=timedelta(seconds=max(0.0, float(retry_timer_seconds))),
        executor_factory=executor_factory,
    )(_execute)


def _register_schedule(
    pgq,
    *,
    schedule_name: str,
    expression: str,
    fn: Callable[..., Any],
    payload: dict[str, Any] | None = None,
) -> None:
    traced_fn = instrument_entrypoint(f"schedule:{schedule_name}", fn)
    kwargs = dict(payload or {})

    @pgq.schedule(schedule_name, expression)
    async def _scheduled(_schedule) -> None:
        traced_fn(**kwargs)


@asynccontextmanager
async def factory():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "business_suite.settings.prod")

    import django

    django.setup()

    from django.conf import settings
    from pgqueuer import PgQueuer
    from pgqueuer.queries import Queries

    try:
        import psycopg
    except Exception as exc:
        raise RuntimeError("psycopg is required for PgQueuer runtime.") from exc

    database = settings.DATABASES.get("default", {})
    connection = await psycopg.AsyncConnection.connect(
        dbname=database.get("NAME") or "",
        user=database.get("USER") or "",
        password=database.get("PASSWORD") or "",
        host=database.get("HOST") or "",
        port=database.get("PORT") or "",
        autocommit=True,
    )

    try:
        queries = Queries.from_psycopg_connection(connection)
        await queries.install()
        await queries.upgrade()

        pgq = PgQueuer.from_psycopg_connection(connection)

        from core.tasks.ai_usage import ENTRYPOINT_CAPTURE_AI_USAGE_TASK, capture_ai_usage_task
        from core.tasks.calendar_reminders import (
            ENTRYPOINT_DISPATCH_DUE_CALENDAR_REMINDERS_TASK,
            dispatch_due_calendar_reminders_task,
        )
        from core.tasks.calendar_sync import (
            ENTRYPOINT_CREATE_GOOGLE_EVENT_TASK,
            ENTRYPOINT_DELETE_GOOGLE_EVENT_TASK,
            ENTRYPOINT_UPDATE_GOOGLE_EVENT_TASK,
            create_google_event_task,
            delete_google_event_task,
            update_google_event_task,
        )
        from core.tasks.cron_jobs import (
            ENTRYPOINT_RUN_AUDITLOG_PRUNE_NOW,
            ENTRYPOINT_RUN_CLEAR_CACHE_NOW,
            ENTRYPOINT_RUN_FULL_BACKUP_NOW,
            ENTRYPOINT_RUN_OPENROUTER_HEALTH_CHECK_NOW,
            run_auditlog_prune_now,
            run_clear_cache_now,
            run_full_backup_now,
            run_openrouter_health_check_now,
        )
        from core.tasks.document_categorization import (
            ENTRYPOINT_RUN_DOCUMENT_CATEGORIZATION_ITEM,
            run_document_categorization_item,
        )
        from core.tasks.document_ocr import ENTRYPOINT_RUN_DOCUMENT_OCR_JOB, run_document_ocr_job
        from core.tasks.document_validation import ENTRYPOINT_RUN_DOCUMENT_VALIDATION, run_document_validation
        from core.tasks.local_resilience import (
            ENTRYPOINT_PULL_REMOTE_CHANGES_TASK,
            ENTRYPOINT_PUSH_LOCAL_CHANGES_TASK,
            pull_remote_changes_task,
            push_local_changes_task,
        )
        from core.tasks.ocr import ENTRYPOINT_RUN_OCR_JOB, run_ocr_job
        from customer_applications.tasks import (
            ENTRYPOINT_CLEANUP_APPLICATION_STORAGE_FOLDER_TASK,
            ENTRYPOINT_CLEANUP_DOCUMENT_STORAGE_TASK,
            ENTRYPOINT_POLL_WHATSAPP_DELIVERY_STATUSES_TASK,
            ENTRYPOINT_SEND_DUE_TOMORROW_CUSTOMER_NOTIFICATIONS_TASK,
            ENTRYPOINT_SYNC_APPLICATION_CALENDAR_TASK,
            cleanup_application_storage_folder_task,
            cleanup_document_storage_task,
            poll_whatsapp_delivery_statuses_task,
            send_due_tomorrow_customer_notifications_task,
            sync_application_calendar_task,
        )
        from customers.tasks import ENTRYPOINT_CHECK_PASSPORT_UPLOADABILITY_TASK, check_passport_uploadability_task
        from invoices.tasks.document_jobs import ENTRYPOINT_RUN_INVOICE_DOCUMENT_JOB, run_invoice_document_job
        from invoices.tasks.download_jobs import ENTRYPOINT_RUN_INVOICE_DOWNLOAD_JOB, run_invoice_download_job
        from invoices.tasks.import_jobs import ENTRYPOINT_RUN_INVOICE_IMPORT_ITEM, run_invoice_import_item
        from products.tasks.product_excel_jobs import (
            ENTRYPOINT_RUN_PRODUCT_EXPORT_JOB,
            ENTRYPOINT_RUN_PRODUCT_IMPORT_JOB,
            run_product_export_job,
            run_product_import_job,
        )

        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_RUN_OCR_JOB,
            fn=run_ocr_job,
            retry_timer_seconds=10,
            executor_factory=_fixed_retry_executor_factory(max_attempts=3, delay_seconds=10),
        )
        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_RUN_DOCUMENT_OCR_JOB, fn=run_document_ocr_job)
        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_DISPATCH_DUE_CALENDAR_REMINDERS_TASK,
            fn=dispatch_due_calendar_reminders_task,
        )
        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_PUSH_LOCAL_CHANGES_TASK, fn=push_local_changes_task)
        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_PULL_REMOTE_CHANGES_TASK, fn=pull_remote_changes_task)
        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_RUN_DOCUMENT_VALIDATION, fn=run_document_validation)
        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_CREATE_GOOGLE_EVENT_TASK,
            fn=create_google_event_task,
            retry_timer_seconds=15,
            executor_factory=_fixed_retry_executor_factory(max_attempts=4, delay_seconds=15),
        )
        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_UPDATE_GOOGLE_EVENT_TASK,
            fn=update_google_event_task,
            retry_timer_seconds=15,
            executor_factory=_fixed_retry_executor_factory(max_attempts=4, delay_seconds=15),
        )
        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_DELETE_GOOGLE_EVENT_TASK,
            fn=delete_google_event_task,
            retry_timer_seconds=15,
            executor_factory=_fixed_retry_executor_factory(max_attempts=4, delay_seconds=15),
        )
        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_RUN_DOCUMENT_CATEGORIZATION_ITEM,
            fn=run_document_categorization_item,
        )
        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_CAPTURE_AI_USAGE_TASK, fn=capture_ai_usage_task)
        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_RUN_INVOICE_DOWNLOAD_JOB, fn=run_invoice_download_job)
        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_RUN_INVOICE_DOCUMENT_JOB, fn=run_invoice_document_job)
        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_RUN_INVOICE_IMPORT_ITEM, fn=run_invoice_import_item)
        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_RUN_PRODUCT_EXPORT_JOB, fn=run_product_export_job)
        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_RUN_PRODUCT_IMPORT_JOB, fn=run_product_import_job)
        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_CLEANUP_DOCUMENT_STORAGE_TASK,
            fn=cleanup_document_storage_task,
        )
        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_CLEANUP_APPLICATION_STORAGE_FOLDER_TASK,
            fn=cleanup_application_storage_folder_task,
        )
        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_SYNC_APPLICATION_CALENDAR_TASK,
            fn=sync_application_calendar_task,
        )
        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_POLL_WHATSAPP_DELIVERY_STATUSES_TASK,
            fn=poll_whatsapp_delivery_statuses_task,
        )
        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_SEND_DUE_TOMORROW_CUSTOMER_NOTIFICATIONS_TASK,
            fn=send_due_tomorrow_customer_notifications_task,
        )
        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_CHECK_PASSPORT_UPLOADABILITY_TASK,
            fn=check_passport_uploadability_task,
        )

        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_RUN_FULL_BACKUP_NOW, fn=run_full_backup_now)
        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_RUN_CLEAR_CACHE_NOW, fn=run_clear_cache_now)
        _register_sync_entrypoint(pgq=pgq, entrypoint=ENTRYPOINT_RUN_AUDITLOG_PRUNE_NOW, fn=run_auditlog_prune_now)
        _register_sync_entrypoint(
            pgq=pgq,
            entrypoint=ENTRYPOINT_RUN_OPENROUTER_HEALTH_CHECK_NOW,
            fn=run_openrouter_health_check_now,
        )

        _register_schedule(
            pgq,
            schedule_name="core.dispatch_due_calendar_reminders",
            expression="*/1 * * * *",
            fn=dispatch_due_calendar_reminders_task,
        )
        _register_schedule(
            pgq,
            schedule_name="core.sync_push_periodic",
            expression="*/1 * * * *",
            fn=push_local_changes_task,
        )
        _register_schedule(
            pgq,
            schedule_name="core.sync_pull_periodic",
            expression="*/1 * * * *",
            fn=pull_remote_changes_task,
        )
        _register_schedule(
            pgq,
            schedule_name="customer_applications.poll_whatsapp_delivery_statuses",
            expression="*/5 * * * *",
            fn=poll_whatsapp_delivery_statuses_task,
        )
        _register_schedule(
            pgq,
            schedule_name="customer_applications.send_due_tomorrow_customer_notifications",
            expression=(
                f"{int(getattr(settings, 'CUSTOMER_NOTIFICATIONS_DAILY_MINUTE', 0))} "
                f"{int(getattr(settings, 'CUSTOMER_NOTIFICATIONS_DAILY_HOUR', 8))} * * *"
            ),
            fn=send_due_tomorrow_customer_notifications_task,
        )

        try:
            backup_hour, backup_minute = _parse_hhmm(getattr(settings, "FULL_BACKUP_SCHEDULE", "02:00"))
            _register_schedule(
                pgq,
                schedule_name="core.full_backup_daily",
                expression=f"{backup_minute} {backup_hour} * * *",
                fn=run_full_backup_now,
            )
        except ValueError as exc:
            logger.error(str(exc))

        clear_cache_schedules = getattr(settings, "CLEAR_CACHE_SCHEDULE", ["03:00"])
        for schedule in clear_cache_schedules:
            try:
                hour, minute = _parse_hhmm(schedule)
            except ValueError as exc:
                logger.error(str(exc))
                continue
            _register_schedule(
                pgq,
                schedule_name=f"core.clear_cache_{hour:02d}{minute:02d}",
                expression=f"{minute} {hour} * * *",
                fn=run_clear_cache_now,
            )

        audit_schedule = str(getattr(settings, "AUDITLOG_RETENTION_SCHEDULE", "04:00") or "").strip()
        if audit_schedule:
            try:
                hour, minute = _parse_hhmm(audit_schedule)
                _register_schedule(
                    pgq,
                    schedule_name="core.auditlog_prune_daily",
                    expression=f"{minute} {hour} * * *",
                    fn=run_auditlog_prune_now,
                )
            except ValueError as exc:
                logger.error(str(exc))

        if bool(getattr(settings, "OPENROUTER_HEALTHCHECK_ENABLED", True)):
            minute_expr = str(getattr(settings, "OPENROUTER_HEALTHCHECK_CRON_MINUTE", "*/5") or "*/5")
            _register_schedule(
                pgq,
                schedule_name="core.openrouter_health_check",
                expression=f"{minute_expr} * * * *",
                fn=run_openrouter_health_check_now,
            )

        logger.info("PgQueuer worker initialized")
        yield pgq
    finally:
        await connection.close()
