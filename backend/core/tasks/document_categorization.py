import traceback as tb_module

from core.services.ai_client import get_ai_user_message, is_ai_timeout_exception
from core.services.ai_document_categorizer import AIDocumentCategorizer, get_document_types_for_prompt
from core.services.logger_service import Logger
from core.tasks.idempotency import acquire_task_lock, build_task_lock_key, release_task_lock
from core.tasks.runtime import QUEUE_REALTIME, db_task, retry_on_transient_external_failure
from customer_applications.models import DocumentCategorizationItem, DocumentCategorizationJob
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from products.models.document_type import DocumentType

logger = Logger.get_logger(__name__)
_TERMINAL_VALIDATION_STATUSES = {"valid", "invalid", "error"}


def _get_categorization_item_result(item: DocumentCategorizationItem) -> dict:
    return item.result if isinstance(item.result, dict) else {}


def categorization_item_ai_validation_enabled(item: DocumentCategorizationItem) -> bool:
    return bool(_get_categorization_item_result(item).get("ai_validation_enabled"))


def categorization_item_has_terminal_validation(item: DocumentCategorizationItem) -> bool:
    if not categorization_item_ai_validation_enabled(item):
        return True
    return str(item.validation_status or "").strip().lower() in _TERMINAL_VALIDATION_STATUSES


def categorization_item_is_terminal(item: DocumentCategorizationItem) -> bool:
    if item.status == DocumentCategorizationItem.STATUS_ERROR:
        return True
    if item.status != DocumentCategorizationItem.STATUS_CATEGORIZED:
        return False
    return categorization_item_has_terminal_validation(item)


@db_task(
    context=True,
    queue=QUEUE_REALTIME,
    queue_defaults=True,
    retry_when=retry_on_transient_external_failure,
)
def run_document_categorization_item(item_id: str, task=None) -> None:
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
        current_result = item.result if isinstance(item.result, dict) else {}
        current_result.update({"stage": "categorizing_pass_1"})
        item.result = current_result
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
                has_slot = item.document_id is not None
                ai_validation_enabled = bool(doc_type.ai_validation and has_slot)
            else:
                item.status = DocumentCategorizationItem.STATUS_ERROR
                item.error_message = result.get("reasoning", "No matching document type found")
                ai_validation_enabled = False
                has_slot = False

            item.confidence = result.get("confidence", 0)
            item.result = {
                "document_type": doc_type_name,
                "document_type_id": doc_type_id,
                "confidence": result.get("confidence", 0),
                "reasoning": result.get("reasoning", ""),
                "pass_used": pass_used,
                "ai_validation_enabled": ai_validation_enabled,
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
            if item.status == DocumentCategorizationItem.STATUS_CATEGORIZED and doc_type_id and ai_validation_enabled:
                from customer_applications.models.doc_application import DocApplication as _DocApp

                product_prompt = (
                    _DocApp.objects.filter(pk=job.doc_application_id)
                    .values_list("product__validation_prompt", flat=True)
                    .first()
                    or ""
                )
                _run_validation_step(item, file_bytes, doc_type, document_types, provider_order, product_prompt)
            elif item.status == DocumentCategorizationItem.STATUS_CATEGORIZED:
                current_result = item.result or {}
                current_result["stage"] = "categorized"
                current_result["ai_validation_enabled"] = False
                if not has_slot:
                    current_result["validation_skipped_reason"] = "no_slot"
                elif doc_type_id and not bool(doc_type.ai_validation):
                    current_result["validation_skipped_reason"] = "doc_type_ai_validation_disabled"
                else:
                    current_result["validation_skipped_reason"] = "validation_not_applicable"
                item.result = current_result
                # Keep DB-compatible empty status when AI validation is skipped.
                item.validation_status = ""
                item.validation_result = None
                item.save(update_fields=["result", "validation_status", "validation_result", "updated_at"])

        except Exception as exc:
            if task and task.retries > 0 and retry_on_transient_external_failure(task.retries_used, exc):
                user_message = get_ai_user_message(exc)
                logger.warning(
                    "Document categorization retry scheduled for item %s on attempt %s/%s. retries_remaining=%s time_limit_ms=%s error=%s",
                    item_id,
                    getattr(task, "attempt", "?"),
                    getattr(task, "max_retries", 0) + 1 if task else "?",
                    task.retries,
                    getattr(task, "time_limit_ms", None),
                    exc,
                )
                current_result = item.result if isinstance(item.result, dict) else {}
                current_result.update(
                    {
                        "stage": "retrying",
                        "ai_validation_enabled": False,
                        "retryable_error": user_message,
                    }
                )
                item.status = DocumentCategorizationItem.STATUS_PROCESSING
                item.error_message = user_message
                item.traceback = ""
                item.result = current_result
                item.save(update_fields=["status", "error_message", "traceback", "result", "updated_at"])
                raise

            full_traceback = tb_module.format_exc()
            logger.error("Document categorization failed for %s: %s\n%s", item.filename, exc, full_traceback)
            item.status = DocumentCategorizationItem.STATUS_ERROR
            item.error_message = str(exc)
            item.traceback = full_traceback
            item.result = {
                "document_type": None,
                "confidence": 0,
                "reasoning": f"Error: {exc}",
                "ai_validation_enabled": False,
                "stage": "error",
            }
            item.save(update_fields=["status", "error_message", "traceback", "result", "updated_at"])

        finally:
            _update_categorization_job_counts(item.job_id)

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
    current_result["ai_validation_enabled"] = True
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
            require_expiration_date=bool(doc_type.has_expiration_date),
            require_doc_number=bool(doc_type.has_doc_number),
            require_details=bool(doc_type.has_details),
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
        user_message = get_ai_user_message(exc)
        runtime_provider = str(getattr(exc, "ai_provider", "") or "").strip().lower() or None
        runtime_provider_name = str(getattr(exc, "ai_provider_name", "") or "").strip() or None
        runtime_model = str(getattr(exc, "ai_model", "") or "").strip() or None
        logger.error(
            "Document validation failed for %s: %s (timeout=%s)",
            item.filename,
            exc,
            is_ai_timeout_exception(exc),
            exc_info=True,
        )
        item.validation_status = "error"
        item.validation_result = {
            "valid": False,
            "confidence": 0,
            "positive_analysis": "",
            "negative_issues": [user_message],
            "reasoning": user_message,
            "extracted_expiration_date": None,
            "extracted_doc_number": None,
            "extracted_details_markdown": None,
            "error_type": "timeout" if is_ai_timeout_exception(exc) else "provider_error",
            "ai_provider": runtime_provider,
            "ai_provider_name": runtime_provider_name or runtime_provider,
            "ai_model": runtime_model,
        }
        current_result = item.result or {}
        current_result["stage"] = "validated"
        current_result["ai_validation_enabled"] = True
        current_result["validation_failed"] = True
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
def _update_categorization_job_counts(job_id) -> None:
    """Atomically recompute parent job counters from item states."""
    job = DocumentCategorizationJob.objects.select_for_update().get(id=job_id)

    items = list(DocumentCategorizationItem.objects.filter(job_id=job_id))
    items_count = len(items)
    if job.total_files != items_count:
        job.total_files = items_count

    success_count = sum(
        1
        for item in items
        if item.status == DocumentCategorizationItem.STATUS_CATEGORIZED and categorization_item_is_terminal(item)
    )
    error_count = sum(1 for item in items if item.status == DocumentCategorizationItem.STATUS_ERROR)
    processed_files = success_count + error_count

    job.success_count = success_count
    job.error_count = error_count
    job.processed_files = processed_files

    if job.total_files:
        job.progress = min(100, int((job.processed_files / job.total_files) * 100))
    else:
        job.progress = 100

    if job.total_files == 0 or job.processed_files >= job.total_files:
        if job.total_files > 0 and job.error_count == job.total_files:
            job.status = DocumentCategorizationJob.STATUS_FAILED
        else:
            job.status = DocumentCategorizationJob.STATUS_COMPLETED
        job.progress = 100

    job.save(
        update_fields=[
            "total_files",
            "processed_files",
            "success_count",
            "error_count",
            "progress",
            "status",
            "updated_at",
        ]
    )
