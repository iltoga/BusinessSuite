from typing import Optional

from core.services.ai_client import AIClient
from core.services.ai_document_categorizer import AIDocumentCategorizer
from core.services.ai_runtime_settings_service import AIRuntimeSettingsService
from core.services.ai_usage_service import AIUsageFeature
from core.utils.document_type_ai_fields import (
    StructuredOutputField,
    build_strict_structured_schema,
    format_fields_for_prompt,
)

def extract_document_structured_output(
    *,
    file_bytes: bytes,
    filename: str,
    doc_type_name: str,
    fields: list[StructuredOutputField],
    model: Optional[str] = None,
    provider_order: Optional[list[str]] = None,
) -> dict:
    if not fields:
        raise ValueError("Structured output fields are required.")

    extractor_model = model or AIRuntimeSettingsService.get_document_ocr_structured_model()

    client = AIClient(
        model=extractor_model,
        feature_name=AIUsageFeature.DOCUMENT_OCR_AI_EXTRACTOR,
    )

    # Reuse the same PDF/image normalization logic used by document categorization.
    categorizer = AIDocumentCategorizer.__new__(AIDocumentCategorizer)
    vision_bytes, vision_filename = categorizer._prepare_vision_bytes(file_bytes, filename)

    field_instructions = format_fields_for_prompt(fields)
    system_prompt = (
        "You are an OCR data extraction assistant for visa and immigration documents.\n"
        f'Extract data from a document classified as "{doc_type_name}".\n'
        "Return ONLY the requested fields using the strict JSON schema.\n"
        "For each field:\n"
        "- Return a string value when it is clearly present.\n"
        "- Return null when the value is missing, unreadable, or uncertain.\n"
        "- Do not guess or hallucinate.\n"
        "- Preserve original document formatting for IDs/codes.\n\n"
        "Fields to extract:\n"
        f"{field_instructions}"
    )
    user_prompt = (
        f"Extract the requested data from this document. Original filename: '{filename}'. "
        "Follow field descriptions exactly."
    )
    messages = client.build_vision_message(
        prompt=user_prompt,
        image_bytes=vision_bytes,
        filename=vision_filename,
        system_prompt=system_prompt,
    )

    extra_kwargs = {}
    if provider_order:
        extra_kwargs["extra_body"] = {"provider": {"order": provider_order}}

    return client.chat_completion_json(
        messages=messages,
        json_schema=build_strict_structured_schema(fields),
        schema_name="document_ocr_structured_output",
        temperature=0.1,
        strict=True,
        **extra_kwargs,
    )
