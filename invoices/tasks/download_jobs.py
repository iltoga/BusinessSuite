import logging
import os
import traceback

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.text import slugify
from huey.contrib.djhuey import db_task

from core.utils.pdf_converter import PDFConverter, PDFConverterError
from invoices.models import InvoiceDownloadJob
from invoices.services.InvoiceService import InvoiceService

logger = logging.getLogger(__name__)


@db_task()
def run_invoice_download_job(job_id: str) -> None:
    try:
        job = InvoiceDownloadJob.objects.select_related("invoice", "invoice__customer").get(id=job_id)
    except InvoiceDownloadJob.DoesNotExist:
        logger.error(f"InvoiceDownloadJob {job_id} not found")
        return

    job.status = InvoiceDownloadJob.STATUS_PROCESSING
    job.progress = 5
    job.save(update_fields=["status", "progress", "updated_at"])

    try:
        invoice = job.invoice
        service = InvoiceService(invoice)

        if invoice.total_paid_amount == 0 or invoice.is_payment_complete:
            data, line_items = service.generate_invoice_data()
            doc_buffer = service.generate_invoice_document(data, line_items)
        else:
            data, line_items, payments = service.generate_partial_invoice_data()
            doc_buffer = service.generate_invoice_document(data, line_items, payments)

        job.progress = 60
        job.save(update_fields=["progress", "updated_at"])

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

        job.progress = 85
        job.save(update_fields=["progress", "updated_at"])

        output_name = f"{safe_name}.{extension}"
        output_path = os.path.join("tmpfiles", "invoice_downloads", str(job.id), output_name)
        saved_path = default_storage.save(output_path, ContentFile(output_bytes))

        job.output_path = saved_path
        job.status = InvoiceDownloadJob.STATUS_COMPLETED
        job.progress = 100
        job.save(update_fields=["output_path", "status", "progress", "updated_at"])

    except Exception as exc:
        full_traceback = traceback.format_exc()
        logger.error(f"Invoice download job {job_id} failed: {str(exc)}\n{full_traceback}")
        job.status = InvoiceDownloadJob.STATUS_FAILED
        job.error_message = str(exc)
        job.traceback = full_traceback
        job.progress = 100
        job.save(update_fields=["status", "error_message", "traceback", "progress", "updated_at"])
