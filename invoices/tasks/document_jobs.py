import logging
import os
import traceback
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.text import slugify
from huey.contrib.djhuey import db_task

from core.utils.pdf_converter import PDFConverter, PDFConverterError
from invoices.models import InvoiceDocumentItem, InvoiceDocumentJob
from invoices.services.InvoiceService import InvoiceService

logger = logging.getLogger(__name__)


@db_task()
def run_invoice_document_job(job_id: str) -> None:
    try:
        job = InvoiceDocumentJob.objects.get(id=job_id)
    except InvoiceDocumentJob.DoesNotExist:
        logger.error(f"InvoiceDocumentJob {job_id} not found")
        return

    job.status = InvoiceDocumentJob.STATUS_PROCESSING
    job.progress = 5
    job.save(update_fields=["status", "progress", "updated_at"])

    items = list(job.items.select_related("invoice").order_by("sort_index"))
    zip_buffer = BytesIO()

    try:
        with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as zip_file:
            for index, item in enumerate(items, start=1):
                item.status = InvoiceDocumentItem.STATUS_PROCESSING
                item.save(update_fields=["status", "updated_at"])

                try:
                    invoice = item.invoice
                    service = InvoiceService(invoice)

                    if invoice.total_paid_amount == 0 or invoice.is_payment_complete:
                        data, line_items = service.generate_invoice_data()
                        doc_buffer = service.generate_invoice_document(data, line_items)
                    else:
                        data, line_items, payments = service.generate_partial_invoice_data()
                        doc_buffer = service.generate_invoice_document(data, line_items, payments)

                    raw_name = f"{invoice.invoice_no_display}_{invoice.customer.full_name}"
                    safe_name = slugify(raw_name, allow_unicode=False).replace("-", "_") or f"Invoice_{invoice.pk}"
                    safe_name = safe_name[:200]

                    if job.format_type == InvoiceDocumentJob.FORMAT_PDF:
                        try:
                            pdf_bytes = PDFConverter.docx_buffer_to_pdf(doc_buffer)
                        except PDFConverterError as exc:
                            raise RuntimeError(str(exc)) from exc
                        filename = f"{safe_name}.pdf"
                        zip_file.writestr(filename, pdf_bytes)
                    else:
                        filename = f"{safe_name}.docx"
                        zip_file.writestr(filename, doc_buffer.getvalue())

                    item.status = InvoiceDocumentItem.STATUS_COMPLETED
                    item.save(update_fields=["status", "updated_at"])

                except Exception as exc:
                    full_traceback = traceback.format_exc()
                    logger.error(
                        f"Failed generating document for invoice {item.invoice_id}: {str(exc)}\n{full_traceback}"
                    )
                    item.status = InvoiceDocumentItem.STATUS_FAILED
                    item.error_message = str(exc)
                    item.traceback = full_traceback
                    item.save(update_fields=["status", "error_message", "traceback", "updated_at"])

                job.processed_invoices = index
                if job.total_invoices:
                    job.progress = int((job.processed_invoices / job.total_invoices) * 100)
                job.save(update_fields=["processed_invoices", "progress", "updated_at"])

        zip_buffer.seek(0)
        output_name = f"invoice_documents_{job.id}.zip"
        output_path = os.path.join("tmpfiles", "invoice_documents", str(job.id), output_name)
        saved_path = default_storage.save(output_path, ContentFile(zip_buffer.getvalue()))

        job.output_path = saved_path
        job.status = InvoiceDocumentJob.STATUS_COMPLETED
        job.progress = 100
        job.save(update_fields=["output_path", "status", "progress", "updated_at"])

    except Exception as exc:
        full_traceback = traceback.format_exc()
        logger.error(f"Invoice document job {job_id} failed: {str(exc)}\n{full_traceback}")
        job.status = InvoiceDocumentJob.STATUS_FAILED
        job.error_message = str(exc)
        job.traceback = full_traceback
        job.progress = 100
        job.save(update_fields=["status", "error_message", "traceback", "progress", "updated_at"])
