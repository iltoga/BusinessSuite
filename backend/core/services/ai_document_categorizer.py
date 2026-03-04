"""
AI Document Categorizer Service

Uses vision-capable LLMs to classify uploaded documents into DocumentType categories.
Supports both single-file categorization and batch processing.
"""

import io
import os
from datetime import date
from typing import Callable, Optional

from core.services.ai_client import (
    AIClient,
    GENERIC_AI_SLOW_RESPONSE,
    get_ai_user_message,
    is_ai_timeout_exception,
)
from core.services.ai_runtime_settings_service import AIRuntimeSettingsService
from core.services.ai_usage_service import AIUsageFeature
from core.services.logger_service import Logger
from core.utils.document_type_ai_fields import format_fields_for_prompt, parse_structured_output_fields
from django.conf import settings
from products.models.document_type import DocumentType

logger = Logger.get_logger(__name__)

# JSON schema for structured output
CATEGORIZATION_SCHEMA = {
    "type": "object",
    "properties": {
        "document_type": {
            "type": ["string", "null"],
            "description": "The exact document type name from the provided list, or null if no match.",
        },
        "confidence": {
            "type": "number",
            "description": "Confidence score between 0.0 and 1.0.",
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of why this document type was chosen.",
        },
    },
    "required": ["document_type", "confidence", "reasoning"],
    "additionalProperties": False,
}

_VALIDATION_REASONING_STRUCTURED_SCHEMA = {
    "type": "object",
    "properties": {
        "missing data": {"type": "array", "items": {"type": "string"}},
        "invalid data": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"}},
        "to do or to ask": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["missing data", "invalid data", "notes", "to do or to ask"],
    "additionalProperties": False,
}

# JSON schema for document validation output
VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "valid": {
            "type": "boolean",
            "description": "Whether the document meets the validation criteria.",
        },
        "confidence": {
            "type": "number",
            "description": "Confidence score between 0.0 and 1.0.",
        },
        "positive_analysis": {
            "type": "string",
            "description": "Summary of which positive criteria the document meets.",
        },
        "negative_issues": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of specific issues found based on negative validation criteria. Empty if valid.",
        },
        "reasoning": {
            "anyOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}},
                {"type": "null"},
                _VALIDATION_REASONING_STRUCTURED_SCHEMA,
            ],
            "description": (
                "Concise operational summary for the validation verdict. "
                "For invalid results, prefer short sectioned output using: "
                "'missing data', 'invalid data', 'notes', and 'to do or to ask'. "
                "Can be plain text or a structured object/array."
            ),
        },
        "extracted_expiration_date": {
            "type": ["string", "null"],
            "description": (
                "Extracted document expiration date in YYYY-MM-DD format when requested, otherwise null."
            ),
        },
        "extracted_doc_number": {
            "type": ["string", "null"],
            "description": "Extracted main document code/number when requested, otherwise null.",
        },
        "extracted_details_markdown": {
            "type": ["string", "null"],
            "description": (
                "Extracted main document data formatted as markdown when requested, otherwise null."
            ),
        },
    },
    "required": [
        "valid",
        "confidence",
        "positive_analysis",
        "negative_issues",
        "reasoning",
        "extracted_expiration_date",
        "extracted_doc_number",
        "extracted_details_markdown",
    ],
    "additionalProperties": False,
}


_REASONING_SECTION_ORDER = ("missing data", "invalid data", "notes", "to do or to ask")
_MISSING_DATA_HINTS = (
    "missing",
    "not visible",
    "not shown",
    "not found",
    "not provided",
    "not present",
    "unreadable",
    "cannot read",
    "can't read",
    "absent",
)
_INVALID_DATA_HINTS = (
    "invalid",
    "expired",
    "mismatch",
    "does not match",
    "do not match",
    "incorrect",
    "inconsistent",
    "tampered",
    "altered",
)


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _normalize_negative_issues(raw_issues: object) -> list[str]:
    if not isinstance(raw_issues, list):
        return []
    normalized: list[str] = []
    for issue in raw_issues:
        if issue is None:
            continue
        text = _normalize_text(str(issue))
        if text:
            normalized.append(text)
    return _dedupe_preserve_order(normalized)


def _normalize_reasoning_items(raw_value: object) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        text = _normalize_text(raw_value)
        return [text] if text else []
    if isinstance(raw_value, dict):
        normalized: list[str] = []
        for key, value in raw_value.items():
            key_text = _normalize_text(str(key))
            nested_items = _normalize_reasoning_items(value)
            if not nested_items:
                continue
            if not key_text:
                normalized.extend(nested_items)
            elif len(nested_items) == 1:
                normalized.append(f"{key_text}: {nested_items[0]}")
            else:
                normalized.append(f"{key_text}: {'; '.join(nested_items)}")
        return _dedupe_preserve_order(normalized)
    if isinstance(raw_value, (list, tuple, set)):
        normalized: list[str] = []
        for entry in raw_value:
            normalized.extend(_normalize_reasoning_items(entry))
        return _dedupe_preserve_order(normalized)

    text = _normalize_text(str(raw_value))
    return [text] if text else []


def _stringify_reasoning(reasoning: object) -> str:
    if reasoning is None:
        return ""
    if isinstance(reasoning, str):
        return reasoning
    if isinstance(reasoning, dict):
        lines: list[str] = []
        for raw_key, raw_value in reasoning.items():
            items = _normalize_reasoning_items(raw_value)
            if not items:
                continue

            section_key = _normalize_text(str(raw_key)).strip(" :").lower()
            heading = section_key if section_key in _REASONING_SECTION_ORDER else _normalize_text(str(raw_key))
            if heading:
                lines.append(f"{heading}:")
                lines.extend(f"- {item}" for item in items[:4])
            else:
                lines.extend(f"- {item}" for item in items[:4])

        if lines:
            return "\n".join(lines)
    if isinstance(reasoning, (list, tuple, set)):
        items = _normalize_reasoning_items(reasoning)
        if items:
            return "\n".join(f"- {item}" for item in items[:8])

    return str(reasoning)


def _extract_structured_reasoning_sections(reasoning: str) -> dict[str, list[str]]:
    sections = {section: [] for section in _REASONING_SECTION_ORDER}
    if not reasoning:
        return {}

    current_section: str | None = None
    has_structured_labels = False
    for raw_line in reasoning.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        normalized = line.lower()
        matched_section: str | None = None
        for section in _REASONING_SECTION_ORDER:
            section_with_colon = f"{section}:"
            if normalized.startswith(section_with_colon):
                has_structured_labels = True
                matched_section = section
                current_section = section
                remainder = _normalize_text(line[len(section_with_colon) :].strip(" -"))
                if remainder:
                    sections[section].append(remainder)
                break
            if normalized == section:
                has_structured_labels = True
                matched_section = section
                current_section = section
                break

        if matched_section:
            continue

        item = line[1:].strip() if line.startswith(("-", "*")) else line
        item = _normalize_text(item)
        if not item:
            continue
        target_section = current_section or "notes"
        sections[target_section].append(item)

    if not has_structured_labels:
        return {}

    for section in _REASONING_SECTION_ORDER:
        sections[section] = _dedupe_preserve_order(sections[section])
    return sections


def _is_missing_data_issue(issue: str) -> bool:
    lower = issue.lower()
    return any(hint in lower for hint in _MISSING_DATA_HINTS)


def _is_invalid_data_issue(issue: str) -> bool:
    lower = issue.lower()
    return any(hint in lower for hint in _INVALID_DATA_HINTS)


def _build_reasoning_sections_from_issues(
    issues: list[str], reasoning: str, structured_sections: dict[str, list[str]]
) -> dict[str, list[str]]:
    sections = {section: [] for section in _REASONING_SECTION_ORDER}

    if structured_sections:
        for section in _REASONING_SECTION_ORDER:
            sections[section] = _dedupe_preserve_order(structured_sections.get(section, []))
    else:
        for issue in issues:
            if _is_missing_data_issue(issue):
                sections["missing data"].append(issue)
            elif _is_invalid_data_issue(issue):
                sections["invalid data"].append(issue)
            else:
                sections["notes"].append(issue)

    if not sections["notes"] and reasoning and not structured_sections and not issues:
        sections["notes"].append(reasoning)

    if (sections["missing data"] or sections["invalid data"]) and not sections["to do or to ask"]:
        if sections["missing data"]:
            sections["to do or to ask"].append(
                "Request a replacement document that includes the missing data listed above."
            )
        if sections["invalid data"]:
            sections["to do or to ask"].append("Correct or replace the invalid data listed above.")
    elif sections["notes"] and not sections["to do or to ask"]:
        sections["to do or to ask"].append(
            "Ask the issuer or uploader for clarification and a corrected file if needed."
        )

    for section in _REASONING_SECTION_ORDER:
        sections[section] = _dedupe_preserve_order(
            [item for item in (_normalize_text(value) for value in sections[section]) if item]
        )
    return sections


def _render_reasoning_sections(sections: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for section in _REASONING_SECTION_ORDER:
        items = sections.get(section, [])
        if not items:
            continue
        lines.append(f"{section}:")
        for item in items[:4]:
            lines.append(f"- {item}")
    return "\n".join(lines).strip()


def format_validation_reasoning(valid: bool, reasoning: object, negative_issues: object) -> str:
    """
    Normalize validation reasoning to concise, operator-friendly text.

    For invalid documents, always emit optional sections in this order:
    missing data, invalid data, notes, to do or to ask.
    """
    reasoning_text = _stringify_reasoning(reasoning)
    normalized_reasoning = _normalize_text(reasoning_text)
    if valid:
        return normalized_reasoning or "valid: all required checks passed."

    issues = _normalize_negative_issues(negative_issues)
    structured_sections = _extract_structured_reasoning_sections(reasoning_text)
    sections = _build_reasoning_sections_from_issues(issues, normalized_reasoning, structured_sections)
    rendered = _render_reasoning_sections(sections)
    if rendered:
        return rendered

    return (
        "notes:\n"
        "- Validation failed.\n"
        "to do or to ask:\n"
        "- Review the document and upload a corrected version."
    )


def extract_validation_expiration_date(validation_result: dict) -> date | None:
    """Return parsed expiration date from validation result, if present and valid."""
    raw_value = validation_result.get("extracted_expiration_date")
    if not raw_value:
        return None

    if not isinstance(raw_value, str):
        logger.warning("Invalid extracted_expiration_date type: %s", type(raw_value).__name__)
        return None

    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        logger.warning("Invalid extracted_expiration_date format: %s", raw_value)
        return None


def extract_validation_doc_number(validation_result: dict) -> str | None:
    """Return normalized extracted document number from validation result, if present."""
    raw_value = validation_result.get("extracted_doc_number")
    if raw_value is None:
        return None

    if not isinstance(raw_value, str):
        logger.warning("Invalid extracted_doc_number type: %s", type(raw_value).__name__)
        return None

    normalized = raw_value.strip()
    return normalized or None


def extract_validation_details_markdown(validation_result: dict) -> str | None:
    """Return normalized markdown details from validation result, if present."""
    raw_value = validation_result.get("extracted_details_markdown")
    if raw_value is None:
        return None

    if not isinstance(raw_value, str):
        logger.warning("Invalid extracted_details_markdown type: %s", type(raw_value).__name__)
        return None

    normalized = raw_value.strip()
    return normalized or None


def _collect_ai_runtime_metadata(client: AIClient) -> dict[str, str]:
    """Collect provider/model metadata from an AI client instance."""
    provider = str(getattr(client, "provider_key", "") or "").strip().lower()
    provider_name = str(getattr(client, "provider_name", "") or "").strip()
    model = str(getattr(client, "model", "") or "").strip()
    return {
        "ai_provider": provider,
        "ai_provider_name": provider_name or provider,
        "ai_model": model,
    }


def _attach_ai_runtime_metadata(target: dict, metadata: dict[str, str]) -> None:
    """Attach provider/model metadata to a validation payload."""
    provider = str(metadata.get("ai_provider") or "").strip().lower()
    provider_name = str(metadata.get("ai_provider_name") or "").strip()
    model = str(metadata.get("ai_model") or "").strip()

    if provider:
        target["ai_provider"] = provider
    if provider_name:
        target["ai_provider_name"] = provider_name
    if model:
        target["ai_model"] = model


def _attach_ai_runtime_metadata_to_exception(exc: Exception, metadata: dict[str, str]) -> None:
    """Expose provider/model metadata on an exception for downstream handlers."""
    provider = str(metadata.get("ai_provider") or "").strip().lower()
    provider_name = str(metadata.get("ai_provider_name") or "").strip()
    model = str(metadata.get("ai_model") or "").strip()

    if provider:
        setattr(exc, "ai_provider", provider)
    if provider_name:
        setattr(exc, "ai_provider_name", provider_name)
    if model:
        setattr(exc, "ai_model", model)


def _build_system_prompt(document_types: list[dict]) -> str:
    """Build the system prompt with the list of valid document types."""
    type_list = "\n".join(
        f"- {dt['name']}" + (f": {dt['description']}" if dt.get("description") else "") for dt in document_types
    )
    return (
        "You are a document classifier for a visa/immigration processing agency in Bali, Indonesia. "
        "You must classify the uploaded document into EXACTLY one of the following document categories:\n\n"
        f"{type_list}\n\n"
        "Rules:\n"
        "1. Return the EXACT document type name from the list above (case-sensitive match).\n"
        "2. If the document clearly does not match any category, return document_type as null.\n"
        "3. Provide a confidence score between 0.0 (no confidence) and 1.0 (certain).\n"
        "4. Provide brief reasoning for your classification.\n"
        "5. Common document types in visa processing:\n"
        "   - 'Passport' = passport bio-data page or full passport scan\n"
        "   - 'Selfie Photo' = a selfie or portrait photo of a person\n"
        "   - 'Flight Ticket' = airline ticket, boarding pass, or flight itinerary\n"
        "   - 'ITK' = Indonesian immigration tax payment (ITK/PNBP receipt)\n"
        "   - 'Surat Permohonan dan Jaminan' = application and guarantee letter for Indonesian immigration\n"
        "   - 'Bank Statement' = bank account statement\n"
        "   - 'Proof of Payment' = payment receipt, transfer confirmation, or invoice for immigration fees\n"
        "   - 'Arrival Stamp' = passport page showing entry/arrival stamp\n"
        "   - 'KTP Sponsor' = Indonesian national ID card (KTP) of a sponsor\n"
        "   - 'Address' = proof of address document\n"
        "6. For multi-page PDFs, classify based on the primary/first page content.\n"
        "7. If the document is a combined/merged PDF with multiple document types, "
        "classify it based on the most prominent document type visible."
    )


def _build_user_prompt(filename: str) -> str:
    """Build the user prompt for classification."""
    return (
        f"Classify this document. The original filename is: '{filename}'. "
        "Analyze the visual content of the document and return the classification result."
    )


def get_document_types_for_prompt() -> list[dict]:
    """Fetch all DocumentType records formatted for the prompt."""
    return list(
        DocumentType.objects.values(
            "id",
            "name",
            "description",
            "validation_rule_ai_positive",
            "validation_rule_ai_negative",
            "ai_structured_output",
        ).order_by("name")
    )


class AIDocumentCategorizer:
    """Classifies documents into DocumentType categories using vision AI."""

    def __init__(
        self,
        model: Optional[str] = None,
        provider_order: Optional[list[str]] = None,
        feature_name: str = AIUsageFeature.DOCUMENT_AI_CATEGORIZER,
        timeout: Optional[float] = None,
    ):
        self.model = model or AIRuntimeSettingsService.get_document_categorizer_model()
        self.provider_order = provider_order
        self.feature_name = feature_name
        self.timeout = float(timeout or getattr(settings, "DOCUMENT_CATEGORIZATION_TIMEOUT", 30.0))
        self._client = None

    def _get_client(self) -> AIClient:
        if self._client is None:
            kwargs = {"feature_name": self.feature_name}
            if self.model:
                kwargs["model"] = self.model
            if self.timeout:
                kwargs["timeout"] = self.timeout
            self._client = AIClient(**kwargs)
        return self._client

    @staticmethod
    def _pdf_to_image_bytes(pdf_bytes: bytes) -> bytes:
        """Convert first page of a PDF to a JPEG image for vision APIs."""
        try:
            from pdf2image import convert_from_bytes

            images = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=200)
            if images:
                buf = io.BytesIO()
                images[0].save(buf, format="JPEG", quality=85)
                return buf.getvalue()
        except Exception as exc:
            logger.warning("pdf2image conversion failed, trying PyPDF: %s", exc)

        # Fallback: try pypdf to extract embedded images
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(pdf_bytes))
            if reader.pages:
                page = reader.pages[0]
                for image_key in page.images:
                    return image_key.data
        except Exception as exc:
            logger.warning("PyPDF image extraction also failed: %s", exc)

        raise ValueError("Could not convert PDF to image for vision API")

    def _prepare_vision_bytes(self, file_bytes: bytes, filename: str) -> tuple[bytes, str]:
        """
        Prepare file bytes for vision API.
        Converts PDFs to JPEG images since most vision APIs don't support PDF as image_url.

        Returns:
            Tuple of (image_bytes, filename_for_mime_detection)
        """
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".pdf" or file_bytes[:5] == b"%PDF-":
            logger.debug("Converting PDF '%s' to image for vision API", filename)
            image_bytes = self._pdf_to_image_bytes(file_bytes)
            return image_bytes, filename.rsplit(".", 1)[0] + ".jpg"
        return file_bytes, filename

    def categorize_file(
        self,
        file_bytes: bytes,
        filename: str,
        document_types: Optional[list[dict]] = None,
    ) -> dict:
        """
        Classify a single file into a DocumentType.

        Args:
            file_bytes: Raw file content
            filename: Original filename (used for MIME detection and context)
            document_types: List of dicts with 'id', 'name', 'description'.
                          If None, fetches from DB.

        Returns:
            Dict with 'document_type' (name or None), 'confidence' (float),
            'reasoning' (str), and 'document_type_id' (int or None).
        """
        if document_types is None:
            document_types = get_document_types_for_prompt()

        client = self._get_client()

        system_prompt = _build_system_prompt(document_types)
        user_prompt = _build_user_prompt(filename)

        # Convert PDFs to images for vision API compatibility
        vision_bytes, vision_filename = self._prepare_vision_bytes(file_bytes, filename)

        messages = client.build_vision_message(
            prompt=user_prompt,
            image_bytes=vision_bytes,
            filename=vision_filename,
            system_prompt=system_prompt,
        )

        extra_kwargs = {}
        if self.provider_order:
            extra_kwargs["extra_body"] = {"provider": {"order": self.provider_order}}

        result = client.chat_completion_json(
            messages=messages,
            json_schema=CATEGORIZATION_SCHEMA,
            schema_name="document_categorization",
            temperature=0.1,
            strict=True,
            retry_on_invalid_json=False,
            **extra_kwargs,
        )

        # Resolve document_type name to ID
        doc_type_name = result.get("document_type")
        doc_type_id = None
        if doc_type_name:
            for dt in document_types:
                if dt["name"] == doc_type_name:
                    doc_type_id = dt["id"]
                    break
            if doc_type_id is None:
                logger.warning(
                    "AI returned document_type '%s' which doesn't match any known type. " "Setting to null.",
                    doc_type_name,
                )
                result["document_type"] = None

        result["document_type_id"] = doc_type_id

        logger.info(
            "Document categorized: %s -> %s (confidence: %.2f)",
            filename,
            result.get("document_type", "UNKNOWN"),
            result.get("confidence", 0),
        )

        return result

    def validate_file_matches_type(
        self,
        file_bytes: bytes,
        filename: str,
        expected_type_name: str,
        document_types: Optional[list[dict]] = None,
    ) -> dict:
        """
        Check if a file matches an expected DocumentType.

        Returns:
            Dict with 'matches' (bool), 'detected_type', 'confidence', 'reasoning'.
        """
        result = self.categorize_file(file_bytes, filename, document_types)

        detected = result.get("document_type")
        matches = detected is not None and detected == expected_type_name

        return {
            "matches": matches,
            "expected_type": expected_type_name,
            "detected_type": detected,
            "confidence": result.get("confidence", 0),
            "reasoning": result.get("reasoning", ""),
            "document_type_id": result.get("document_type_id"),
        }

    def categorize_file_two_pass(
        self,
        file_bytes: bytes,
        filename: str,
        document_types: Optional[list[dict]] = None,
        on_pass_update: Optional[Callable[[int, str], None]] = None,
    ) -> dict:
        """
        Two-pass categorization with automatic fallback to a higher-tier model.

        Pass 1 uses the primary model (self.model).
        If pass 1 returns document_type=None, pass 2 uses DOCUMENT_CATEGORIZER_MODEL_HIGH.

        Args:
            file_bytes: Raw file content.
            filename: Original filename.
            document_types: Pre-fetched document types list; fetched from DB if None.
            on_pass_update: Optional callback(pass_number, message) for progress updates.

        Returns:
            Dict with categorization result plus 'pass_used' (1 or 2).
        """
        if document_types is None:
            document_types = get_document_types_for_prompt()

        # --- Pass 1 ---
        if on_pass_update:
            on_pass_update(1, f"Categorizing {filename} (pass 1)...")

        try:
            result = self.categorize_file(file_bytes, filename, document_types)
        except Exception as exc:
            logger.warning("Pass 1 failed for %s: %s", filename, exc)
            result = {
                "document_type": None,
                "confidence": 0,
                "reasoning": (
                    GENERIC_AI_SLOW_RESPONSE
                    if is_ai_timeout_exception(exc)
                    else get_ai_user_message(exc)
                ),
                "_skip_pass_2": True,
            }

        if result.get("document_type_id"):
            result["pass_used"] = 1
            return result

        if result.get("_skip_pass_2"):
            result.pop("_skip_pass_2", None)
            result["pass_used"] = 1
            return result

        # --- Pass 2: fallback to higher-tier model ---
        high_model = AIRuntimeSettingsService.get_document_categorizer_model_high()
        if not high_model or high_model == self.model:
            # No distinct fallback configured
            result["pass_used"] = 1
            return result

        if on_pass_update:
            on_pass_update(2, f"Retrying {filename} with higher-tier model (pass 2)...")

        logger.info("Pass 1 returned no match for %s, retrying with model %s", filename, high_model)

        high_categorizer = AIDocumentCategorizer(
            model=high_model,
            provider_order=self.provider_order,
            feature_name=self.feature_name,
            timeout=self.timeout,
        )
        try:
            result2 = high_categorizer.categorize_file(file_bytes, filename, document_types)
        except Exception as exc:
            logger.warning("Pass 2 failed for %s: %s", filename, exc)
            result2 = {
                "document_type": None,
                "confidence": 0,
                "reasoning": (
                    GENERIC_AI_SLOW_RESPONSE
                    if is_ai_timeout_exception(exc)
                    else get_ai_user_message(exc)
                ),
            }

        result2["pass_used"] = 2
        return result2

    @staticmethod
    def validate_document(
        file_bytes: bytes,
        filename: str,
        doc_type_name: str,
        positive_prompt: str,
        negative_prompt: str,
        product_prompt: str = "",
        require_expiration_date: bool = False,
        require_doc_number: bool = False,
        require_details: bool = False,
        model: Optional[str] = None,
        provider_order: Optional[list[str]] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """
        Validate a document against its DocumentType's positive/negative criteria.

        Uses a dedicated validator model (DOCUMENT_VALIDATOR_MODEL).
        If no prompts are configured, returns an auto-valid result without calling the LLM.

        Returns:
            Dict with 'valid' (bool), 'confidence' (float), 'positive_analysis' (str),
            'negative_issues' (list[str]), 'reasoning' (str), and
            extraction fields:
            - 'extracted_expiration_date' (YYYY-MM-DD string or null)
            - 'extracted_doc_number' (string or null)
            - 'extracted_details_markdown' (markdown string or null)
        """
        if not positive_prompt and not negative_prompt and not product_prompt:
            return {
                "valid": True,
                "confidence": 1.0,
                "positive_analysis": "No validation rules configured for this document type.",
                "negative_issues": [],
                "reasoning": "Validation skipped — no AI validation prompts defined.",
                "extracted_expiration_date": None,
                "extracted_doc_number": None,
                "extracted_details_markdown": None,
            }

        validator_model = model or AIRuntimeSettingsService.get_document_validator_model()
        validation_timeout = float(timeout or getattr(settings, "DOCUMENT_VALIDATION_TIMEOUT", 30.0))
        client = AIClient(
            model=validator_model,
            feature_name=AIUsageFeature.DOCUMENT_AI_VALIDATOR,
            timeout=validation_timeout,
        )

        normalized_negative_prompt = negative_prompt
        negative_fields = parse_structured_output_fields(negative_prompt)
        if negative_fields:
            normalized_negative_prompt = (
                "Flag document as invalid when any required extraction field is missing or unreliable:\n"
                f"{format_fields_for_prompt(negative_fields)}"
            )

        # Build system prompt incorporating both positive and negative rules
        sections = [
            f"You are a document quality validator for a visa/immigration agency. "
            f'You are validating a document classified as "{doc_type_name}".\n'
        ]
        if positive_prompt:
            sections.append(f"POSITIVE VALIDATION CRITERIA (the document SHOULD meet these):\n{positive_prompt}\n")
        if normalized_negative_prompt:
            sections.append(
                "NEGATIVE VALIDATION CRITERIA (the document should NOT have these issues):\n"
                f"{normalized_negative_prompt}\n"
            )
        if product_prompt:
            sections.append(
                f"PRODUCT-SPECIFIC CONTEXT (applies to this visa/product and takes priority over generic rules):\n{product_prompt}\n"
            )
        if require_expiration_date:
            sections.append(
                "MANDATORY EXPIRATION DATE EXTRACTION:\n"
                "- Extract the document expiration date from the document image/content.\n"
                "- Return it in 'extracted_expiration_date' using YYYY-MM-DD format.\n"
                "- If the date is missing or unreadable, return null.\n"
                "- Do not guess or hallucinate."
            )
        else:
            sections.append(
                "Set 'extracted_expiration_date' to null unless expiration-date extraction is explicitly required."
            )
        if require_doc_number:
            sections.append(
                "MANDATORY DOCUMENT NUMBER EXTRACTION:\n"
                "- Extract the main document code/number/ID from the document.\n"
                "- Return only the code value in 'extracted_doc_number'.\n"
                "- If missing or unreadable, return null.\n"
                "- Do not add labels, comments, or guessed values."
            )
        else:
            sections.append("Set 'extracted_doc_number' to null unless document-number extraction is required.")
        if require_details:
            sections.append(
                "MANDATORY DETAILS EXTRACTION:\n"
                "- Extract only the main document data and return it as markdown in 'extracted_details_markdown'.\n"
                "- Use concise markdown (headings and/or bullet points) containing only document facts.\n"
                "- Do not add comments, explanations, warnings, or recommendations.\n"
                "- If no reliable data can be extracted, return null."
            )
        else:
            sections.append("Set 'extracted_details_markdown' to null unless details extraction is required.")
        sections.append(
            "Analyze the uploaded image/document against both sets of criteria.\n"
            "Return valid=true ONLY if the document reasonably meets the positive criteria "
            "AND has no major negative issues.\n"
            "List each specific negative issue found in 'negative_issues' (empty array if none).\n"
            "Provide an overall confidence score (0.0-1.0).\n"
            "For invalid results, keep 'reasoning' concise and structured using only these optional sections, "
            "in this order: missing data, invalid data, notes, to do or to ask.\n"
            "Use short bullet lines ('- ...') under each included section and skip empty sections.\n"
            "For valid results, keep 'reasoning' to one short sentence.\n"
            "Always include 'extracted_expiration_date', 'extracted_doc_number', and "
            "'extracted_details_markdown'."
        )
        system_prompt = "\n".join(sections)
        user_prompt = (
            f"Validate this document (classified as '{doc_type_name}'). "
            f"Original filename: '{filename}'. "
            "Check it against the positive and negative validation criteria."
        )

        # Prepare vision bytes (PDF → image if needed)
        categorizer = AIDocumentCategorizer.__new__(AIDocumentCategorizer)
        vision_bytes, vision_filename = categorizer._prepare_vision_bytes(file_bytes, filename)

        messages = client.build_vision_message(
            prompt=user_prompt,
            image_bytes=vision_bytes,
            filename=vision_filename,
            system_prompt=system_prompt,
        )

        extra_kwargs = {}
        if provider_order:
            extra_kwargs["extra_body"] = {"provider": {"order": provider_order}}

        try:
            result = client.chat_completion_json(
                messages=messages,
                json_schema=VALIDATION_SCHEMA,
                schema_name="document_validation",
                temperature=0.1,
                strict=True,
                retry_on_invalid_json=False,
                **extra_kwargs,
            )
        except Exception as exc:
            _attach_ai_runtime_metadata_to_exception(exc, _collect_ai_runtime_metadata(client))
            raise

        result["negative_issues"] = _normalize_negative_issues(result.get("negative_issues"))
        result["reasoning"] = format_validation_reasoning(
            valid=bool(result.get("valid")),
            reasoning=result.get("reasoning"),
            negative_issues=result.get("negative_issues"),
        )
        _attach_ai_runtime_metadata(result, _collect_ai_runtime_metadata(client))

        logger.info(
            "Document validated: %s (%s) -> valid=%s (confidence: %.2f)",
            filename,
            doc_type_name,
            result.get("valid"),
            result.get("confidence", 0),
        )

        return result
