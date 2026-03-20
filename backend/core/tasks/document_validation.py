"""
Dramatiq task for AI validation of a single uploaded document.

Triggered after a document file is uploaded/updated when the user
opts in to AI validation. Updates Document.ai_validation_status
and Document.ai_validation_result so the SSE endpoint can stream
progress to the frontend.
"""

import traceback as tb_module

from core.services.ai_client import get_ai_user_message, is_ai_timeout_exception
from core.services.ai_document_categorizer import (
    AIDocumentCategorizer,
    build_document_validation_prompts,
    extract_validation_details_markdown,
    extract_validation_doc_number,
    extract_validation_expiration_date,
    format_validation_reasoning,
)
from core.services.logger_service import Logger
from core.tasks.idempotency import acquire_task_lock, build_task_lock_key, release_task_lock
from core.tasks.runtime import QUEUE_REALTIME, db_task, retry_on_transient_external_failure
from customer_applications.models import Document
from customer_applications.services.document_expiration_state_service import DocumentExpirationStateService
from django.core.files.storage import default_storage

logger = Logger.get_logger(__name__)


def _apply_expiration_metadata(document: Document, validation: dict) -> tuple[dict, bool]:
    expiration_state = DocumentExpirationStateService().evaluate(document)
    validation["expiration_state"] = expiration_state.state
    validation["expiration_reason"] = expiration_state.reason
    validation["expiration_threshold_days"] = expiration_state.threshold_days

    if not expiration_state.is_invalid:
        return validation, bool(validation.get("valid", False))

    issues_raw = validation.get("negative_issues")
    if isinstance(issues_raw, list):
        issues = [str(issue).strip() for issue in issues_raw if str(issue).strip()]
    elif issues_raw:
        issues = [str(issues_raw).strip()]
    else:
        issues = []

    if expiration_state.reason and expiration_state.reason not in issues:
        issues.append(expiration_state.reason)

    validation["negative_issues"] = issues
    validation["reasoning"] = format_validation_reasoning(
        valid=False,
        reasoning=validation.get("reasoning", ""),
        negative_issues=issues,
    )
    validation["valid"] = False
    return validation, False


@db_task(
    context=True,
    queue=QUEUE_REALTIME,
    queue_defaults=True,
    retry_when=retry_on_transient_external_failure,
)
def run_document_validation(document_id: int, task=None) -> None:
    """Validate a single document file against its document-type and product prompts."""
    lock_key = build_task_lock_key(namespace="doc_upload_validation", item_id=str(document_id))
    lock_token = acquire_task_lock(lock_key)
    if not lock_token:
        logger.warning("Document validation task skipped (lock contention): document_id=%s", document_id)
        return

    try:
        try:
            document = Document.objects.select_related("doc_type", "doc_application__product").get(id=document_id)
        except Document.DoesNotExist:
            logger.error("Document %s not found for validation", document_id)
            return

        # Mark as validating
        document.ai_validation_status = Document.AI_VALIDATION_VALIDATING
        document.ai_validation_result = None
        document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])

        doc_type = document.doc_type
        product = document.doc_application.product if document.doc_application else None

        if not doc_type or not doc_type.ai_validation:
            document.ai_validation_status = Document.AI_VALIDATION_NONE
            document.ai_validation_result = None
            document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])
            return

        positive_prompt = doc_type.validation_rule_ai_positive if doc_type else ""
        negative_prompt = doc_type.validation_rule_ai_negative if doc_type else ""
        product_prompt = product.validation_prompt if product else ""

        if not positive_prompt and not negative_prompt and not product_prompt:
            validation = {
                "valid": True,
                "confidence": 1.0,
                "positive_analysis": "No validation rules configured.",
                "negative_issues": [],
                "reasoning": "Validation skipped — no AI validation prompts defined.",
                "extracted_expiration_date": None,
                "extracted_doc_number": None,
                "extracted_details_markdown": None,
            }
            validation, is_valid = _apply_expiration_metadata(document, validation)
            document.ai_validation_status = Document.AI_VALIDATION_VALID if is_valid else Document.AI_VALIDATION_INVALID
            document.ai_validation_result = validation
            document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])
            return

        # Read file bytes
        if not document.file or not document.file.name:
            document.ai_validation_status = Document.AI_VALIDATION_ERROR
            document.ai_validation_result = {
                "valid": False,
                "confidence": 0,
                "positive_analysis": "",
                "negative_issues": ["Document has no file attached."],
                "reasoning": "Cannot validate a document without a file.",
                "extracted_expiration_date": None,
                "extracted_doc_number": None,
                "extracted_details_markdown": None,
            }
            document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])
            return

        try:
            with default_storage.open(document.file.name, "rb") as fh:
                file_bytes = fh.read()
        except Exception as exc:
            logger.error("Cannot read file for document %s: %s", document_id, exc)
            document.ai_validation_status = Document.AI_VALIDATION_ERROR
            document.ai_validation_result = {
                "valid": False,
                "confidence": 0,
                "positive_analysis": "",
                "negative_issues": [f"Could not read file: {exc}"],
                "reasoning": "File read error.",
                "extracted_expiration_date": None,
                "extracted_doc_number": None,
                "extracted_details_markdown": None,
            }
            document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])
            return

        filename = document.file.name.split("/")[-1] if "/" in document.file.name else document.file.name

        system_prompt, user_prompt = build_document_validation_prompts(
            filename=filename,
            doc_type_name=doc_type.name,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            product_prompt=product_prompt,
            require_expiration_date=bool(doc_type.has_expiration_date),
            require_doc_number=bool(doc_type.has_doc_number),
            require_details=bool(doc_type.has_details),
        )
        logger.info(
            "Document validation system prompt for document %s (%s):\n%s",
            document_id,
            filename,
            system_prompt,
        )
        logger.info(
            "Document validation user prompt for document %s (%s):\n%s",
            document_id,
            filename,
            user_prompt,
        )

        try:
            validation = AIDocumentCategorizer.validate_document(
                file_bytes=file_bytes,
                filename=filename,
                doc_type_name=doc_type.name,
                positive_prompt=positive_prompt,
                negative_prompt=negative_prompt,
                product_prompt=product_prompt,
                require_expiration_date=bool(doc_type.has_expiration_date),
                require_doc_number=bool(doc_type.has_doc_number),
                require_details=bool(doc_type.has_details),
            )

            update_fields = {"updated_at"}

            extracted_expiration_date = extract_validation_expiration_date(validation)
            if doc_type.has_expiration_date and extracted_expiration_date:
                document.expiration_date = extracted_expiration_date
                update_fields.update({"expiration_date", "completed"})

            extracted_doc_number = extract_validation_doc_number(validation)
            if doc_type.has_doc_number and extracted_doc_number:
                document.doc_number = extracted_doc_number
                update_fields.update({"doc_number", "completed"})

            extracted_details_markdown = extract_validation_details_markdown(validation)
            if doc_type.has_details and extracted_details_markdown and not (document.details or "").strip():
                document.details = extracted_details_markdown
                update_fields.update({"details", "completed"})

            validation, is_valid = _apply_expiration_metadata(document, validation)
            document.ai_validation_status = Document.AI_VALIDATION_VALID if is_valid else Document.AI_VALIDATION_INVALID
            document.ai_validation_result = validation
            update_fields.update({"ai_validation_status", "ai_validation_result"})

            document.save(update_fields=list(update_fields))

            logger.info(
                "Document %s validated: valid=%s (confidence=%.2f)",
                document_id,
                is_valid,
                validation.get("confidence", 0),
            )

        except Exception as exc:
            full_tb = tb_module.format_exc()
            logger.error("AI validation failed for document %s: %s\n%s", document_id, exc, full_tb)
            user_message = get_ai_user_message(exc)
            runtime_provider = str(getattr(exc, "ai_provider", "") or "").strip().lower() or None
            runtime_provider_name = str(getattr(exc, "ai_provider_name", "") or "").strip() or None
            runtime_model = str(getattr(exc, "ai_model", "") or "").strip() or None

            if task and task.retries > 0 and retry_on_transient_external_failure(task.retries_used, exc):
                logger.warning(
                    "Document validation retry scheduled for document %s on attempt %s/%s. retries_remaining=%s time_limit_ms=%s error_type=%s",
                    document_id,
                    getattr(task, "attempt", "?"),
                    getattr(task, "max_retries", 0) + 1 if task else "?",
                    task.retries,
                    getattr(task, "time_limit_ms", None),
                    "timeout" if is_ai_timeout_exception(exc) else "provider_error",
                )
                document.ai_validation_status = Document.AI_VALIDATION_VALIDATING
                document.ai_validation_result = {
                    "status": "retrying",
                    "message": user_message,
                    "error_type": "timeout" if is_ai_timeout_exception(exc) else "provider_error",
                    "retries_remaining": task.retries,
                    "ai_provider": runtime_provider,
                    "ai_provider_name": runtime_provider_name or runtime_provider,
                    "ai_model": runtime_model,
                }
                document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])
                raise

            document.ai_validation_status = Document.AI_VALIDATION_ERROR
            document.ai_validation_result = {
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
            document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])

    finally:
        release_task_lock(lock_key, lock_token)
