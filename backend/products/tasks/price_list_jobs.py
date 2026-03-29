"""Async jobs for generating and distributing product price lists."""

import os
import traceback

from core.models import AsyncJob
from core.services.logger_service import Logger
from core.tasks.idempotency import acquire_task_lock, build_task_lock_key, release_task_lock
from core.tasks.progress import persist_progress
from core.tasks.runtime import QUEUE_REALTIME, db_task
from core.utils.pdf_converter import PDFConverter, PDFConverterError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from products.services.price_list_service import ProductPriceListService

logger = Logger.get_logger(__name__)


@db_task(queue=QUEUE_REALTIME)
def run_product_price_list_print_job(job_id: str, user_id: int | None = None) -> None:
    lock_key = build_task_lock_key(namespace="products_price_list_print_job", item_id=str(job_id))
    lock_token = acquire_task_lock(lock_key)
    if not lock_token:
        logger.warning("Product price list print task skipped due to lock contention: job_id=%s", job_id)
        return

    try:
        try:
            job = AsyncJob.objects.get(id=job_id)
        except AsyncJob.DoesNotExist:
            logger.error("AsyncJob %s not found for product price list print", job_id)
            return

        try:
            service = ProductPriceListService()
            persist_progress(
                job,
                progress=5,
                status=AsyncJob.STATUS_PROCESSING,
                force=True,
                extra_fields={"message": "Collecting active products for the public price list..."},
            )

            sections = service.build_sections()
            persist_progress(
                job,
                progress=35,
                force=True,
                extra_fields={"message": "Designing grouped printable price list..."},
            )

            docx_buffer, summary = service.generate_docx_buffer(sections, generated_at=timezone.localtime())
            persist_progress(
                job,
                progress=72,
                force=True,
                extra_fields={"message": "Converting printable price list to PDF..."},
            )

            pdf_bytes = PDFConverter.docx_buffer_to_pdf(docx_buffer)
            persist_progress(
                job,
                progress=90,
                force=True,
                extra_fields={"message": "Saving printable price list..."},
            )

            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
            filename = f"public_price_list_{timestamp}.pdf"
            output_path = os.path.join("tmpfiles", "product_price_lists", str(job.id), filename)
            saved_path = default_storage.save(output_path, ContentFile(pdf_bytes))

            job.complete(
                result={
                    "file_path": saved_path,
                    "filename": filename,
                    "content_type": "application/pdf",
                    **summary,
                },
                message=(
                    "Printable price list ready "
                    f"({summary['total_products']} products across {summary['total_categories']} categories)."
                ),
            )
        except PDFConverterError as exc:
            logger.error("Product price list PDF conversion failed for job %s: %s", job_id, str(exc), exc_info=True)
            job.fail(f"Price list PDF conversion failed: {exc}", traceback.format_exc())
        except Exception as exc:
            logger.error("Product price list print job %s failed: %s", job_id, str(exc), exc_info=True)
            job.fail(str(exc), traceback.format_exc())
    finally:
        release_task_lock(lock_key, lock_token)
