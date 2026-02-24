"""
AI Document Categorizer Service

Uses vision-capable LLMs to classify uploaded documents into DocumentType categories.
Supports both single-file categorization and batch processing.
"""

from typing import Optional

from core.services.ai_client import AIClient
from core.services.ai_usage_service import AIUsageFeature
from core.services.logger_service import Logger
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
    return list(DocumentType.objects.values("id", "name", "description").order_by("name"))


class AIDocumentCategorizer:
    """Classifies documents into DocumentType categories using vision AI."""

    def __init__(
        self,
        model: Optional[str] = None,
        provider_order: Optional[list[str]] = None,
        feature_name: str = AIUsageFeature.DOCUMENT_AI_CATEGORIZER,
    ):
        self.model = model
        self.provider_order = provider_order
        self.feature_name = feature_name
        self._client = None

    def _get_client(self) -> AIClient:
        if self._client is None:
            kwargs = {"feature_name": self.feature_name}
            if self.model:
                kwargs["model"] = self.model
            self._client = AIClient(**kwargs)
        return self._client

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

        messages = client.build_vision_message(
            prompt=user_prompt,
            image_bytes=file_bytes,
            filename=filename,
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
