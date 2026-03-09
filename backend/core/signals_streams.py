from __future__ import annotations

from api.utils.stream_payloads import (
    serialize_async_job_payload,
    serialize_document_ocr_job_payload,
    serialize_invoice_download_job_payload,
    serialize_invoice_import_item_payload,
    serialize_invoice_import_job_payload,
    serialize_ocr_job_payload,
)
from core.models import AsyncJob, CalendarReminder, DocumentOCRJob, OCRJob
from core.services.logger_service import Logger
from core.services.redis_streams import publish_stream_event as _publish_stream_event
from core.services.redis_streams import stream_file_key, stream_job_key, stream_user_key
from customer_applications.models import Document, WorkflowNotification
from customer_applications.models.categorization_job import DocumentCategorizationItem, DocumentCategorizationJob
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from invoices.models import (
    InvoiceDocumentItem,
    InvoiceDocumentJob,
    InvoiceDownloadJob,
    InvoiceImportItem,
    InvoiceImportJob,
)

WORKFLOW_STREAM_KEY = stream_job_key("workflow-notifications")
logger = Logger.get_logger(__name__)
# Backward-compatible symbol for tests/patches that reference the old import name.
publish_stream_event = _publish_stream_event


def _publish_stream_event_safe(stream_key: str, **kwargs) -> None:
    def _emit() -> None:
        try:
            _publish_stream_event(stream_key, **kwargs)
        except Exception as exc:
            logger.warning(
                "Stream publish skipped (stream_key=%s, event=%s): %s",
                stream_key,
                kwargs.get("event"),
                exc,
            )

    try:
        transaction.on_commit(_emit)
    except Exception:
        _emit()


@receiver(post_save, sender=AsyncJob, dispatch_uid="streams_async_job_post_save")
def streams_async_job_post_save(sender, instance: AsyncJob, created, **kwargs):
    payload = serialize_async_job_payload(instance)
    _publish_stream_event_safe(
        stream_job_key(instance.id),
        event="async_job_status",
        status=instance.status,
        payload=payload,
        job_id=str(instance.id),
        user_id=str(instance.created_by_id) if instance.created_by_id else None,
    )


@receiver(post_save, sender=OCRJob, dispatch_uid="streams_ocr_job_post_save")
def streams_ocr_job_post_save(sender, instance: OCRJob, created, **kwargs):
    payload = serialize_ocr_job_payload(instance)
    _publish_stream_event_safe(
        stream_job_key(instance.id),
        event="ocr_job_changed",
        status=instance.status,
        payload=payload,
        job_id=str(instance.id),
        user_id=str(instance.created_by_id) if instance.created_by_id else None,
    )


@receiver(post_save, sender=DocumentOCRJob, dispatch_uid="streams_document_ocr_job_post_save")
def streams_document_ocr_job_post_save(sender, instance: DocumentOCRJob, created, **kwargs):
    payload = serialize_document_ocr_job_payload(instance)
    _publish_stream_event_safe(
        stream_job_key(instance.id),
        event="document_ocr_job_changed",
        status=instance.status,
        payload=payload,
        job_id=str(instance.id),
        user_id=str(instance.created_by_id) if instance.created_by_id else None,
    )


@receiver(post_save, sender=InvoiceDownloadJob, dispatch_uid="streams_invoice_download_job_post_save")
def streams_invoice_download_job_post_save(sender, instance: InvoiceDownloadJob, created, **kwargs):
    payload = serialize_invoice_download_job_payload(instance)
    _publish_stream_event_safe(
        stream_job_key(instance.id),
        event="invoice_download_job_changed",
        status=instance.status,
        payload=payload,
        job_id=str(instance.id),
        user_id=str(instance.created_by_id) if instance.created_by_id else None,
    )


@receiver(post_save, sender=InvoiceImportJob, dispatch_uid="streams_invoice_import_job_post_save")
def streams_invoice_import_job_post_save(sender, instance: InvoiceImportJob, created, **kwargs):
    payload = serialize_invoice_import_job_payload(instance)
    _publish_stream_event_safe(
        stream_job_key(instance.id),
        event="invoice_import_job_changed",
        status=instance.status,
        payload=payload,
        job_id=str(instance.id),
        user_id=str(instance.created_by_id) if instance.created_by_id else None,
    )


@receiver(post_save, sender=InvoiceImportItem, dispatch_uid="streams_invoice_import_item_post_save")
def streams_invoice_import_item_post_save(sender, instance: InvoiceImportItem, created, **kwargs):
    payload = serialize_invoice_import_item_payload(instance)
    _publish_stream_event_safe(
        stream_job_key(instance.job_id),
        event="invoice_import_item_changed",
        status=instance.status,
        payload=payload,
        job_id=str(instance.job_id),
    )


@receiver(post_save, sender=InvoiceDocumentJob, dispatch_uid="streams_invoice_document_job_post_save")
def streams_invoice_document_job_post_save(sender, instance: InvoiceDocumentJob, created, **kwargs):
    payload = {
        "jobId": str(instance.id),
        "status": instance.status,
        "progress": instance.progress,
        "totalInvoices": instance.total_invoices,
        "processedInvoices": instance.processed_invoices,
        "errorMessage": instance.error_message,
    }
    _publish_stream_event_safe(
        stream_job_key(instance.id),
        event="invoice_document_job_changed",
        status=instance.status,
        payload=payload,
        job_id=str(instance.id),
        user_id=str(instance.created_by_id) if instance.created_by_id else None,
    )


@receiver(post_save, sender=InvoiceDocumentItem, dispatch_uid="streams_invoice_document_item_post_save")
def streams_invoice_document_item_post_save(sender, instance: InvoiceDocumentItem, created, **kwargs):
    payload = {
        "itemId": str(instance.id),
        "jobId": str(instance.job_id),
        "index": instance.sort_index,
        "status": instance.status,
        "invoiceId": instance.invoice_id,
        "errorMessage": instance.error_message,
    }
    _publish_stream_event_safe(
        stream_job_key(instance.job_id),
        event="invoice_document_item_changed",
        status=instance.status,
        payload=payload,
        job_id=str(instance.job_id),
    )


@receiver(post_save, sender=DocumentCategorizationJob, dispatch_uid="streams_categorization_job_post_save")
def streams_categorization_job_post_save(sender, instance: DocumentCategorizationJob, created, **kwargs):
    payload = {
        "jobId": str(instance.id),
        "status": instance.status,
        "progress": instance.progress,
        "totalFiles": instance.total_files,
        "processedFiles": instance.processed_files,
        "successCount": instance.success_count,
        "errorCount": instance.error_count,
        "result": instance.result,
        "errorMessage": instance.error_message,
    }
    _publish_stream_event_safe(
        stream_job_key(instance.id),
        event="categorization_job_changed",
        status=instance.status,
        payload=payload,
        job_id=str(instance.id),
        user_id=str(instance.created_by_id) if instance.created_by_id else None,
    )


@receiver(post_save, sender=DocumentCategorizationItem, dispatch_uid="streams_categorization_item_post_save")
def streams_categorization_item_post_save(sender, instance: DocumentCategorizationItem, created, **kwargs):
    payload = {
        "itemId": str(instance.id),
        "jobId": str(instance.job_id),
        "index": instance.sort_index,
        "filename": instance.filename,
        "status": instance.status,
        "result": instance.result,
        "validationStatus": instance.validation_status,
        "validationResult": instance.validation_result,
        "errorMessage": instance.error_message,
    }
    _publish_stream_event_safe(
        stream_job_key(instance.job_id),
        event="categorization_item_changed",
        status=instance.status,
        payload=payload,
        job_id=str(instance.job_id),
    )


@receiver(post_save, sender=Document, dispatch_uid="streams_document_post_save")
def streams_document_post_save(sender, instance: Document, created, **kwargs):
    if not (
        instance.ai_validation_status
        or instance.ai_validation_result
        or instance.doc_type.ai_validation
        or kwargs.get("update_fields")
    ):
        return

    payload = {
        "documentId": instance.id,
        "validationStatus": instance.ai_validation_status,
        "validationResult": instance.ai_validation_result or {},
    }
    _publish_stream_event_safe(
        stream_file_key(instance.id),
        event="document_validation_changed",
        status=instance.ai_validation_status or "pending",
        payload=payload,
        file_id=str(instance.id),
        user_id=(
            str(instance.updated_by_id or instance.created_by_id)
            if (instance.updated_by_id or instance.created_by_id)
            else None
        ),
    )


@receiver(post_save, sender=CalendarReminder, dispatch_uid="streams_calendar_reminder_post_save")
def streams_calendar_reminder_post_save(sender, instance: CalendarReminder, created, **kwargs):
    if not instance.created_by_id:
        return

    payload = {
        "operation": "created" if created else "updated",
        "reminderId": instance.id,
        "ownerId": instance.created_by_id,
    }
    _publish_stream_event_safe(
        stream_user_key(instance.created_by_id),
        event="calendar_reminders_changed",
        status="info",
        payload=payload,
        user_id=str(instance.created_by_id),
    )


@receiver(post_delete, sender=CalendarReminder, dispatch_uid="streams_calendar_reminder_post_delete")
def streams_calendar_reminder_post_delete(sender, instance: CalendarReminder, **kwargs):
    if not instance.created_by_id:
        return

    payload = {
        "operation": "deleted",
        "reminderId": instance.id,
        "ownerId": instance.created_by_id,
    }
    _publish_stream_event_safe(
        stream_user_key(instance.created_by_id),
        event="calendar_reminders_changed",
        status="info",
        payload=payload,
        user_id=str(instance.created_by_id),
    )


@receiver(post_save, sender=WorkflowNotification, dispatch_uid="streams_workflow_notification_post_save")
def streams_workflow_notification_post_save(sender, instance: WorkflowNotification, created, **kwargs):
    payload = {
        "operation": "created" if created else "updated",
        "notificationId": instance.id,
    }
    _publish_stream_event_safe(
        WORKFLOW_STREAM_KEY,
        event="workflow_notifications_changed",
        status="info",
        payload=payload,
    )


@receiver(post_delete, sender=WorkflowNotification, dispatch_uid="streams_workflow_notification_post_delete")
def streams_workflow_notification_post_delete(sender, instance: WorkflowNotification, **kwargs):
    payload = {
        "operation": "deleted",
        "notificationId": instance.id,
    }
    _publish_stream_event_safe(
        WORKFLOW_STREAM_KEY,
        event="workflow_notifications_changed",
        status="info",
        payload=payload,
    )
