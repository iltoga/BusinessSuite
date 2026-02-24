"""
Huey task for AI validation of a single uploaded document.

Triggered after a document file is uploaded/updated when the user
opts in to AI validation. Updates Document.ai_validation_status
and Document.ai_validation_result so the SSE endpoint can stream
progress to the frontend.
"""

import traceback as tb_module

from core.services.ai_document_categorizer import AIDocumentCategorizer
from core.services.logger_service import Logger
from core.tasks.idempotency import acquire_task_lock, build_task_lock_key, release_task_lock
from customer_applications.models import Document
from django.core.files.storage import default_storage
from huey.contrib.djhuey import db_task

logger = Logger.get_logger(__name__)


@db_task()
def run_document_validation(document_id: int) -> None:
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

        positive_prompt = doc_type.validation_rule_ai_positive if doc_type else ""
        negative_prompt = doc_type.validation_rule_ai_negative if doc_type else ""
        product_prompt = product.validation_prompt if product else ""

        if not positive_prompt and not negative_prompt and not product_prompt:
            # Nothing to validate against — mark as skipped/valid
            document.ai_validation_status = Document.AI_VALIDATION_VALID
            document.ai_validation_result = {
                "valid": True,
                "confidence": 1.0,
                "positive_analysis": "No validation rules configured.",
                "negative_issues": [],
                "reasoning": "Validation skipped — no AI validation prompts defined.",
            }
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
            }
            document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])
            return

        filename = document.file.name.split("/")[-1] if "/" in document.file.name else document.file.name

        try:
            validation = AIDocumentCategorizer.validate_document(
                file_bytes=file_bytes,
                filename=filename,
                doc_type_name=doc_type.name,
                positive_prompt=positive_prompt,
                negative_prompt=negative_prompt,
                product_prompt=product_prompt,
            )

            is_valid = validation.get("valid", False)
            document.ai_validation_status = Document.AI_VALIDATION_VALID if is_valid else Document.AI_VALIDATION_INVALID
            document.ai_validation_result = validation
            document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])

            logger.info(
                "Document %s validated: valid=%s (confidence=%.2f)",
                document_id,
                is_valid,
                validation.get("confidence", 0),
            )

        except Exception as exc:
            full_tb = tb_module.format_exc()
            logger.error("AI validation failed for document %s: %s\n%s", document_id, exc, full_tb)
            document.ai_validation_status = Document.AI_VALIDATION_ERROR
            document.ai_validation_result = {
                "valid": False,
                "confidence": 0,
                "positive_analysis": "",
                "negative_issues": [f"Validation error: {exc}"],
                "reasoning": f"Validation could not be completed: {exc}",
            }
            document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])

    finally:
        release_task_lock(lock_key, lock_token)
