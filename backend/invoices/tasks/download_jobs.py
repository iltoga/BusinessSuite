"""Async jobs for invoice download and cleanup workflows."""

"""Async jobs for invoice download and cleanup workflows."""

import os
import traceback
from time import perf_counter

from core.services.logger_service import Logger
from core.tasks.idempotency import acquire_task_lock, build_task_lock_key, release_task_lock
from core.tasks.progress import persist_progress
from core.tasks.runtime import QUEUE_DOC_CONVERSION, db_task
from core.utils.pdf_converter import PDFConverter, PDFConverterError
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.text import slugify
from invoices.models import Invoice, InvoiceDownloadJob
from invoices.services.InvoiceService import InvoiceService

logger = Logger.get_logger(__name__)
INVOICE_DOC_QUEUE = str(
    getattr(settings, "DRAMATIQ_INVOICE_DOC_QUEUE", QUEUE_DOC_CONVERSION) or QUEUE_DOC_CONVERSION
).strip()


@db_task(queue=INVOICE_DOC_QUEUE)
def run_invoice_download_job(job_id: str) -> None:
    lock_key = build_task_lock_key(namespace="invoice_download_job", item_id=str(job_id))
    lock_token = acquire_task_lock(lock_key)
    if not lock_token:
        logger.warning("Invoice download task skipped due to lock contention: job_id=%s", job_id)
        return

    try:
        try:
            job = InvoiceDownloadJob.objects.get(id=job_id)
        except InvoiceDownloadJob.DoesNotExist:
            logger.error(f"InvoiceDownloadJob {job_id} not found")
            return

        if job.status in {InvoiceDownloadJob.STATUS_COMPLETED, InvoiceDownloadJob.STATUS_FAILED}:
            logger.info("Skipping invoice download job already finalized: job_id=%s status=%s", job_id, job.status)
            return

        persist_progress(job, status=InvoiceDownloadJob.STATUS_PROCESSING, progress=5, force=True)

        try:
            invoice = Invoice.objects.for_document_generation().get(id=job.invoice_id)
            service = InvoiceService(invoice)
            started_at = perf_counter()

            if invoice.total_paid_amount == 0 or invoice.is_payment_complete:
                data, line_items = service.generate_invoice_data()
                doc_buffer = service.generate_invoice_document(data, line_items)
            else:
                data, line_items, payments = service.generate_partial_invoice_data()
                doc_buffer = service.generate_invoice_document(data, line_items, payments)
            docx_generated_at = perf_counter()

            persist_progress(job, progress=60, force=True)

            raw_name = f"{invoice.invoice_no_display}_{invoice.customer.full_name}"
            safe_name = slugify(raw_name, allow_unicode=False).replace("-", "_") or f"Invoice_{invoice.pk}"
            safe_name = safe_name[:200]

            if job.format_type == InvoiceDownloadJob.FORMAT_PDF:
                try:
                    output_bytes = PDFConverter.docx_buffer_to_pdf(doc_buffer)
                except PDFConverterError as exc:
                    raise RuntimeError(str(exc)) from exc
                extension = "pdf"
            else:
                output_bytes = doc_buffer.getvalue()
                extension = "docx"
            conversion_completed_at = perf_counter()

            persist_progress(job, progress=85, force=True)

            output_name = f"{safe_name}.{extension}"
            output_path = os.path.join("tmpfiles", "invoice_downloads", str(job.id), output_name)
            saved_path = default_storage.save(output_path, ContentFile(output_bytes))
            saved_at = perf_counter()

            job.output_path = saved_path
            job.status = InvoiceDownloadJob.STATUS_COMPLETED
            job.error_message = ""
            job.traceback = ""
            job.progress = 100
            job.save(update_fields=["output_path", "status", "error_message", "traceback", "progress", "updated_at"])

            logger.info(
                "Invoice download timings job_id=%s format=%s docx_ms=%.1f convert_ms=%.1f store_ms=%.1f total_ms=%.1f",
                job_id,
                job.format_type,
                (docx_generated_at - started_at) * 1000,
                (conversion_completed_at - docx_generated_at) * 1000,
                (saved_at - conversion_completed_at) * 1000,
                (saved_at - started_at) * 1000,
            )

        except Exception as exc:
            full_traceback = traceback.format_exc()
            logger.error(f"Invoice download job {job_id} failed: {str(exc)}\n{full_traceback}")
            job.status = InvoiceDownloadJob.STATUS_FAILED
            job.output_path = ""
            job.error_message = str(exc)
            job.traceback = full_traceback
            job.progress = 100
            job.save(update_fields=["status", "output_path", "error_message", "traceback", "progress", "updated_at"])
    finally:
        release_task_lock(lock_key, lock_token)
