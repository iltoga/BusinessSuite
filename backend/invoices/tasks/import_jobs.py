import logging
import os
import traceback

from core.services.logger_service import Logger
from core.tasks.idempotency import acquire_task_lock, build_task_lock_key, release_task_lock
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from huey.contrib.djhuey import db_task
from invoices.models import InvoiceImportItem, InvoiceImportJob
from invoices.services.invoice_importer import InvoiceImporter
from payments.models import Payment

logger = Logger.get_logger(__name__)


@db_task()
def run_invoice_import_item(item_id: str) -> None:
    lock_key = build_task_lock_key(namespace="invoice_import_item", item_id=str(item_id))
    lock_token = acquire_task_lock(lock_key)
    if not lock_token:
        logger.warning("Invoice import item task skipped due to lock contention: item_id=%s", item_id)
        return

    try:
        try:
            item = InvoiceImportItem.objects.select_related("job").get(id=item_id)
        except InvoiceImportItem.DoesNotExist:
            logger.error(f"InvoiceImportItem {item_id} not found")
            return

        job = item.job

        terminal_item_statuses = {
            InvoiceImportItem.STATUS_IMPORTED,
            InvoiceImportItem.STATUS_DUPLICATE,
            InvoiceImportItem.STATUS_ERROR,
        }
        if item.status in terminal_item_statuses:
            logger.info(
                "Skipping invoice import item already in terminal state: item_id=%s status=%s", item_id, item.status
            )
            _update_invoice_import_job_counts(item.job_id)
            return

        if job.status == InvoiceImportJob.STATUS_QUEUED:
            job.status = InvoiceImportJob.STATUS_PROCESSING
            job.updated_at = timezone.now()
            job.save(update_fields=["status", "updated_at"])

        item.status = InvoiceImportItem.STATUS_PROCESSING
        item.result = {"stage": "queued"}
        item.error_message = ""
        item.traceback = ""
        item.save(update_fields=["status", "result", "error_message", "traceback", "updated_at"])

        try:
            file_name = os.path.basename(item.file_path)

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
                item.traceback = ""
                item.save(update_fields=["status", "result", "error_message", "traceback", "updated_at"])
                return

            with default_storage.open(item.file_path, "rb") as handle:
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
            if item.status != InvoiceImportItem.STATUS_ERROR:
                item.traceback = ""
            item.save(
                update_fields=["status", "result", "invoice", "customer", "error_message", "traceback", "updated_at"]
            )

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
            _update_invoice_import_job_counts(item.job_id)
    finally:
        release_task_lock(lock_key, lock_token)


@transaction.atomic
def _update_invoice_import_job_counts(job_id):
    job = InvoiceImportJob.objects.select_for_update().get(id=job_id)

    items = InvoiceImportItem.objects.filter(job_id=job_id)
    items_count = items.count()
    if job.total_files != items_count:
        job.total_files = items_count
    imported_count = items.filter(status=InvoiceImportItem.STATUS_IMPORTED).count()
    duplicate_count = items.filter(status=InvoiceImportItem.STATUS_DUPLICATE).count()
    error_count = items.filter(status=InvoiceImportItem.STATUS_ERROR).count()
    processed_files = imported_count + duplicate_count + error_count

    job.imported_count = imported_count
    job.duplicate_count = duplicate_count
    job.error_count = error_count
    job.processed_files = processed_files

    if job.total_files:
        job.progress = min(100, int((job.processed_files / job.total_files) * 100))
    else:
        # Empty jobs should not remain stuck in processing
        job.progress = 100

    if job.total_files == 0 or job.processed_files >= job.total_files:
        if job.total_files > 0 and job.error_count == job.total_files:
            job.status = InvoiceImportJob.STATUS_FAILED
        else:
            job.status = InvoiceImportJob.STATUS_COMPLETED
        job.progress = 100

    job.save(
        update_fields=[
            "total_files",
            "processed_files",
            "imported_count",
            "duplicate_count",
            "error_count",
            "progress",
            "status",
            "updated_at",
        ]
    )
