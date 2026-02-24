import traceback as tb_module

from core.services.ai_document_categorizer import AIDocumentCategorizer, get_document_types_for_prompt
from core.services.logger_service import Logger
from core.tasks.idempotency import acquire_task_lock, build_task_lock_key, release_task_lock
from customer_applications.models import DocumentCategorizationItem, DocumentCategorizationJob
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from huey.contrib.djhuey import db_task
from products.models.document_type import DocumentType

logger = Logger.get_logger(__name__)


@db_task()
def run_document_categorization_item(item_id: str) -> None:
    """Categorize a single uploaded file using AI vision (two-pass) and validate."""
    lock_key = build_task_lock_key(namespace="doc_categorization_item", item_id=str(item_id))
    lock_token = acquire_task_lock(lock_key)
    if not lock_token:
        logger.warning("Document categorization task skipped (lock contention): item_id=%s", item_id)
        return

    try:
        try:
            item = DocumentCategorizationItem.objects.select_related("job").get(id=item_id)
        except DocumentCategorizationItem.DoesNotExist:
            logger.error("DocumentCategorizationItem %s not found", item_id)
            return

        job = item.job

        # Mark job as processing on first item
        if job.status == DocumentCategorizationJob.STATUS_QUEUED:
            job.status = DocumentCategorizationJob.STATUS_PROCESSING
            job.updated_at = timezone.now()
            job.save(update_fields=["status", "updated_at"])

        item.status = DocumentCategorizationItem.STATUS_PROCESSING
        item.result = {"stage": "categorizing_pass_1"}
        item.save(update_fields=["status", "result", "updated_at"])

        try:
            with default_storage.open(item.file_path, "rb") as handle:
                file_bytes = handle.read()

            # Get model/provider config from job params
            model = job.request_params.get("model")
            provider_order = job.request_params.get("provider_order")

            categorizer = AIDocumentCategorizer(
                model=model,
                provider_order=provider_order,
            )

            # Fetch document types once
            document_types = get_document_types_for_prompt()

            # Callback to persist pass updates for SSE visibility
            def on_pass_update(pass_num: int, message: str) -> None:
                item.result = {"stage": f"categorizing_pass_{pass_num}", "message": message}
                item.save(update_fields=["result", "updated_at"])

            # --- Two-pass categorization ---
            result = categorizer.categorize_file_two_pass(
                file_bytes=file_bytes,
                filename=item.filename,
                document_types=document_types,
                on_pass_update=on_pass_update,
            )

            doc_type_id = result.get("document_type_id")
            doc_type_name = result.get("document_type")
            pass_used = result.get("pass_used", 1)

            if doc_type_id:
                doc_type = DocumentType.objects.get(id=doc_type_id)
                item.document_type = doc_type
                item.status = DocumentCategorizationItem.STATUS_CATEGORIZED

                # Try to match with an existing Document row in the application
                _try_match_document(item, job.doc_application_id)
            else:
                item.status = DocumentCategorizationItem.STATUS_ERROR
                item.error_message = result.get("reasoning", "No matching document type found")

            item.confidence = result.get("confidence", 0)
            item.result = {
                "document_type": doc_type_name,
                "document_type_id": doc_type_id,
                "confidence": result.get("confidence", 0),
                "reasoning": result.get("reasoning", ""),
                "pass_used": pass_used,
                "stage": "categorized",
            }
            item.save(
                update_fields=[
                    "status",
                    "document_type",
                    "document",
                    "confidence",
                    "result",
                    "error_message",
                    "updated_at",
                ]
            )

            # --- Validation step (only if categorization succeeded) ---
            if item.status == DocumentCategorizationItem.STATUS_CATEGORIZED and doc_type_id:
                from customer_applications.models.doc_application import DocApplication as _DocApp

                product_prompt = (
                    _DocApp.objects.filter(pk=job.doc_application_id)
                    .values_list("product__validation_prompt", flat=True)
                    .first()
                    or ""
                )
                _run_validation_step(item, file_bytes, doc_type, document_types, provider_order, product_prompt)

        except Exception as exc:
            full_traceback = tb_module.format_exc()
            logger.error("Document categorization failed for %s: %s\n%s", item.filename, exc, full_traceback)
            item.status = DocumentCategorizationItem.STATUS_ERROR
            item.error_message = str(exc)
            item.traceback = full_traceback
            item.result = {
                "document_type": None,
                "confidence": 0,
                "reasoning": f"Error: {exc}",
            }
            item.save(update_fields=["status", "error_message", "traceback", "result", "updated_at"])

        finally:
            _update_categorization_job_counts(item.job_id, item.status)

    finally:
        release_task_lock(lock_key, lock_token)


def _run_validation_step(
    item: DocumentCategorizationItem,
    file_bytes: bytes,
    doc_type: DocumentType,
    document_types: list[dict],
    provider_order: list[str] | None,
    product_prompt: str = "",
) -> None:
    """Run AI validation on a categorized item using its DocumentType's positive/negative prompts."""
    positive_prompt = doc_type.validation_rule_ai_positive
    negative_prompt = doc_type.validation_rule_ai_negative

    # Signal validating stage for SSE
    current_result = item.result or {}
    current_result["stage"] = "validating"
    item.result = current_result
    item.save(update_fields=["result", "updated_at"])

    try:
        validation = AIDocumentCategorizer.validate_document(
            file_bytes=file_bytes,
            filename=item.filename,
            doc_type_name=doc_type.name,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            product_prompt=product_prompt,
            provider_order=provider_order,
        )

        item.validation_status = "valid" if validation.get("valid") else "invalid"
        item.validation_result = validation

        # Update result.stage for SSE
        current_result = item.result or {}
        current_result["stage"] = "validated"
        item.result = current_result

        item.save(update_fields=["validation_status", "validation_result", "result", "updated_at"])

    except Exception as exc:
        logger.error("Document validation failed for %s: %s", item.filename, exc, exc_info=True)
        item.validation_status = "invalid"
        item.validation_result = {
            "valid": False,
            "confidence": 0,
            "positive_analysis": "",
            "negative_issues": [f"Validation error: {exc}"],
            "reasoning": f"Validation could not be completed: {exc}",
        }
        current_result = item.result or {}
        current_result["stage"] = "validated"
        item.result = current_result
        item.save(update_fields=["validation_status", "validation_result", "result", "updated_at"])


def _try_match_document(item: DocumentCategorizationItem, doc_application_id: int) -> None:
    """Try to match the categorized item with a Document row in the application."""
    from customer_applications.models import Document

    # Find a document of this type in the application that doesn't have a file yet
    matching_doc = (
        Document.objects.filter(
            doc_application_id=doc_application_id,
            doc_type=item.document_type,
        )
        .order_by("required", "created_at")  # prefer required docs first
        .first()
    )

    if matching_doc:
        item.document = matching_doc


@transaction.atomic
def _update_categorization_job_counts(job_id, item_status: str) -> None:
    """Atomically update parent job counters after an item completes."""
    job = DocumentCategorizationJob.objects.select_for_update().get(id=job_id)
    job.processed_files += 1

    if item_status == DocumentCategorizationItem.STATUS_CATEGORIZED:
        job.success_count += 1
    else:
        job.error_count += 1

    if job.total_files:
        job.progress = int((job.processed_files / job.total_files) * 100)

    if job.processed_files >= job.total_files:
        job.status = DocumentCategorizationJob.STATUS_COMPLETED
        job.progress = 100

    job.save(
        update_fields=[
            "processed_files",
            "success_count",
            "error_count",
            "progress",
            "status",
            "updated_at",
        ]
    )
