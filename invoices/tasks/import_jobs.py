import logging
import os
import traceback

from django.core.files.storage import default_storage
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from huey.contrib.djhuey import db_task

from invoices.models import InvoiceImportItem, InvoiceImportJob
from invoices.services.invoice_importer import InvoiceImporter
from payments.models import Payment

logger = logging.getLogger(__name__)


@db_task()
def run_invoice_import_item(item_id: str) -> None:
    try:
        item = InvoiceImportItem.objects.select_related("job").get(id=item_id)
    except InvoiceImportItem.DoesNotExist:
        logger.error(f"InvoiceImportItem {item_id} not found")
        return

    job = item.job

    if job.status == InvoiceImportJob.STATUS_QUEUED:
        job.status = InvoiceImportJob.STATUS_PROCESSING
        job.updated_at = timezone.now()
        job.save(update_fields=["status", "updated_at"])

    item.status = InvoiceImportItem.STATUS_PROCESSING
    item.result = {"stage": "queued"}
    item.save(update_fields=["status", "result", "updated_at"])

    try:
        abs_path = default_storage.path(item.file_path)
        file_name = os.path.basename(abs_path)

        allowed_extensions = [".pdf", ".xlsx", ".xls", ".docx", ".doc"]
        file_ext = os.path.splitext(file_name.lower())[-1]
        if file_ext not in allowed_extensions:
            error_message = f"Unsupported file format: {file_ext}"
            item.status = InvoiceImportItem.STATUS_ERROR
            item.result = {
                "success": False,
                "status": "error",
                "message": error_message,
                "filename": file_name,
                "errors": [f"File type {file_ext} not supported"],
            }
            item.error_message = error_message
            item.save(update_fields=["status", "result", "error_message", "updated_at"])
            return

        with open(abs_path, "rb") as handle:
            file_bytes = handle.read()

        item.result = {"stage": "parsing"}
        item.save(update_fields=["result", "updated_at"])

        llm_provider = job.request_params.get("llm_provider")
        llm_model = job.request_params.get("llm_model")
        importer = InvoiceImporter(user=job.created_by, llm_provider=llm_provider, llm_model=llm_model)

        result = importer.import_from_file(file_bytes, file_name)

        if result.success and result.status == "imported" and item.is_paid and result.invoice:
            try:
                payment_count = 0
                for invoice_app in result.invoice.invoice_applications.all():
                    Payment.objects.create(
                        invoice_application=invoice_app,
                        from_customer=result.invoice.customer,
                        payment_date=result.invoice.due_date,
                        amount=invoice_app.amount,
                        payment_type=Payment.CASH,
                        notes=f"Auto-created payment for imported invoice {result.invoice.invoice_no_display}",
                        created_by=job.created_by,
                        updated_by=job.created_by,
                    )
                    payment_count += 1
                result.message += f" (Marked as paid with {payment_count} payment(s))"
            except Exception as exc:
                logger.error(f"Error creating payments for {file_name}: {str(exc)}", exc_info=True)
                result.message += " (Warning: Failed to create payments)"

        result_data = {
            "success": result.success,
            "status": result.status,
            "message": result.message,
            "filename": file_name,
        }

        if result.invoice:
            result_data["invoice"] = {
                "id": result.invoice.pk,
                "invoice_no": result.invoice.invoice_no_display,
                "customer_name": result.invoice.customer.full_name,
                "total_amount": str(result.invoice.total_amount),
                "invoice_date": result.invoice.invoice_date.strftime("%Y-%m-%d"),
                "status": result.invoice.get_status_display(),
                "url": reverse("invoice-detail", kwargs={"pk": result.invoice.pk}),
            }

        if result.customer:
            result_data["customer"] = {
                "id": result.customer.pk,
                "name": result.customer.full_name,
            }

        if result.errors:
            result_data["errors"] = result.errors

        if result.status == "imported":
            item.status = InvoiceImportItem.STATUS_IMPORTED
        elif result.status == "duplicate":
            item.status = InvoiceImportItem.STATUS_DUPLICATE
        else:
            item.status = InvoiceImportItem.STATUS_ERROR

        item.result = result_data
        item.invoice = result.invoice if result.invoice else None
        item.customer = result.customer if result.customer else None
        item.error_message = "" if result.success else result_data.get("message", "")
        item.save(update_fields=["status", "result", "invoice", "customer", "error_message", "updated_at"])

    except Exception as exc:
        full_traceback = traceback.format_exc()
        logger.error(f"Invoice import failed for {item.filename}: {str(exc)}\n{full_traceback}")
        item.status = InvoiceImportItem.STATUS_ERROR
        item.error_message = str(exc)
        item.traceback = full_traceback
        item.result = {
            "success": False,
            "status": "error",
            "message": f"Server error: {str(exc)}",
            "filename": item.filename,
            "errors": [str(exc)],
        }
        item.save(update_fields=["status", "error_message", "traceback", "result", "updated_at"])

    finally:
        _update_invoice_import_job_counts(item.job_id, item.status)


@transaction.atomic
def _update_invoice_import_job_counts(job_id, item_status):
    job = InvoiceImportJob.objects.select_for_update().get(id=job_id)
    job.processed_files += 1

    if item_status == InvoiceImportItem.STATUS_IMPORTED:
        job.imported_count += 1
    elif item_status == InvoiceImportItem.STATUS_DUPLICATE:
        job.duplicate_count += 1
    else:
        job.error_count += 1

    if job.total_files:
        job.progress = int((job.processed_files / job.total_files) * 100)

    if job.processed_files >= job.total_files:
        job.status = InvoiceImportJob.STATUS_COMPLETED
        job.progress = 100

    job.save(
        update_fields=[
            "processed_files",
            "imported_count",
            "duplicate_count",
            "error_count",
            "progress",
            "status",
            "updated_at",
        ]
    )
