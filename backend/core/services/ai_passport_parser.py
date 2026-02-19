"""
AI Passport Parser Service
Uses AI vision to extract structured passport data from images.
Supports multimodal vision for passport images, complementing MRZ extraction.
"""

import json
import logging
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Optional, Union

from django.core.files.uploadedfile import UploadedFile

from core.services.ai_client import AIClient
from core.services.ai_usage_service import AIUsageFeature
from core.services.logger_service import Logger
from core.utils.icao_validation import validate_passport_number_icao
from core.utils.imgutils import convert_and_resize_image

logger = Logger.get_logger(__name__)


@dataclass
class PassportData:
    """Structured data for passport information extracted by AI."""

    # Name fields
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None

    # Identity fields
    nationality: Optional[str] = None  # 3-letter country code, e.g., "ITA", "USA"
    nationality_code: Optional[str] = None  # Same as nationality (3-letter code)
    gender: Optional[str] = None  # "M" or "F"

    # Date fields (all in YYYY-MM-DD format)
    date_of_birth: Optional[str] = None
    birth_place: Optional[str] = None  # City/country of birth

    # Passport fields
    passport_number: Optional[str] = None
    passport_issue_date: Optional[str] = None
    passport_expiration_date: Optional[str] = None
    issuing_country: Optional[str] = None  # Country name in English
    issuing_country_code: Optional[str] = None  # 3-letter code
    issuing_authority: Optional[str] = None  # Issuing authority name

    # Physical description
    height_cm: Optional[int] = None  # Height in centimeters
    eye_color: Optional[str] = None  # e.g., "Brown", "Blue", "Green"

    # Address
    address_abroad: Optional[str] = None  # Address in country of residence

    # Document type
    document_type: Optional[str] = None  # Usually "P" for passport

    # Confidence
    confidence_score: float = 0.0


@dataclass
class AIPassportResult:
    """Complete AI parsed passport result."""

    passport_data: PassportData
    raw_response: dict = field(default_factory=dict)
    success: bool = False
    error_message: Optional[str] = None


class AIPassportParser:
    """
    Service to parse passport images using AI vision.
    Extracts structured passport data including fields not available in MRZ.
    """

    # JSON Schema for structured passport output
    PASSPORT_SCHEMA = {
        "type": "object",
        "properties": {
            "first_name": {"type": ["string", "null"]},
            "last_name": {"type": ["string", "null"]},
            "full_name": {"type": ["string", "null"]},
            "nationality": {"type": ["string", "null"]},
            "nationality_code": {"type": ["string", "null"]},
            "gender": {"type": ["string", "null"]},
            "date_of_birth": {"type": ["string", "null"]},
            "birth_place": {"type": ["string", "null"]},
            "passport_number": {"type": ["string", "null"]},
            "passport_issue_date": {"type": ["string", "null"]},
            "passport_expiration_date": {"type": ["string", "null"]},
            "issuing_country": {"type": ["string", "null"]},
            "issuing_country_code": {"type": ["string", "null"]},
            "issuing_authority": {"type": ["string", "null"]},
            "height_cm": {"type": ["integer", "null"]},
            "eye_color": {"type": ["string", "null"]},
            "address_abroad": {"type": ["string", "null"]},
            "document_type": {"type": ["string", "null"]},
            "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": [
            "first_name",
            "last_name",
            "full_name",
            "nationality",
            "nationality_code",
            "gender",
            "date_of_birth",
            "birth_place",
            "passport_number",
            "passport_issue_date",
            "passport_expiration_date",
            "issuing_country",
            "issuing_country_code",
            "issuing_authority",
            "height_cm",
            "eye_color",
            "address_abroad",
            "document_type",
            "confidence_score",
        ],
        "additionalProperties": False,
    }

    # Supported input types. PDFs are accepted and converted to PNG before vision parsing.
    SUPPORTED_TYPES = ["png", "jpg", "jpeg", "gif", "webp", "pdf"]

    # Actual image types accepted by the vision API payload.
    VISION_IMAGE_TYPES = ["png", "jpg", "jpeg", "gif", "webp"]

    # System prompt for passport analysis
    SYSTEM_PROMPT = (
        "You are an expert at extracting structured data from passport documents. "
        "Analyze the passport image carefully and extract all visible information. "
        "Be precise with dates, names, and codes."
    )

    # Maximum retry attempts for passport number validation
    MAX_PASSPORT_VALIDATION_RETRIES = 2

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        use_openrouter: Optional[bool] = None,
    ):
        """
        Initialize the parser.

        Args:
            api_key: API key (defaults to settings)
            model: Model to use (defaults to settings)
            use_openrouter: Whether to use OpenRouter (defaults to settings)
        """
        self.ai_client = AIClient(
            api_key=api_key,
            model=model,
            use_openrouter=use_openrouter,
            feature_name=AIUsageFeature.PASSPORT_OCR_AI_EXTRACTOR,
        )
        logger.info(
            f"Initialized AI Passport parser with {self.ai_client.provider_name} " f"(model: {self.ai_client.model})"
        )

    @property
    def model(self) -> str:
        """Get the model name for backward compatibility."""
        return self.ai_client.model

    @property
    def use_openrouter(self) -> bool:
        """Get whether using OpenRouter for backward compatibility."""
        return self.ai_client.use_openrouter

    def parse_passport_image(
        self,
        file_content: Union[bytes, UploadedFile],
        filename: str = "",
    ) -> AIPassportResult:
        """
        Parse passport image using multimodal vision to extract structured data.

        Args:
            file_content: File bytes or Django UploadedFile
            filename: Original filename for context

        Returns:
            AIPassportResult with extracted passport data
        """
        try:
            # Read file bytes
            file_bytes, detected_filename = AIClient.read_file_bytes(file_content)
            filename = filename or detected_filename

            # Detect and validate file type
            file_type = AIClient.get_file_extension(filename)

            if file_type and file_type not in self.SUPPORTED_TYPES:
                return AIPassportResult(
                    passport_data=PassportData(),
                    success=False,
                    error_message=(
                        f"Unsupported file type: {file_type}. " f"Supported: {', '.join(self.SUPPORTED_TYPES)}"
                    ),
                )

            # If a PDF is provided, convert the first page to PNG bytes for the vision model.
            # This keeps downstream logic (mime type, image_url payload) strictly image-based.
            if file_type == "pdf":
                try:
                    # Use high DPI (300) for maximum quality OCR/vision parsing
                    pil_img, _ = convert_and_resize_image(
                        BytesIO(file_bytes),
                        "application/pdf",
                        return_encoded=False,
                        resize=False,
                        dpi=300,
                    )
                    png_buffer = BytesIO()
                    # Save with lossless compression to preserve quality
                    pil_img.save(png_buffer, format="PNG", compress_level=1, optimize=False)
                    file_bytes = png_buffer.getvalue()

                    # Replace extension so mime type becomes image/png.
                    original_path = Path(filename) if filename else Path("passport.pdf")
                    filename = str(original_path.with_suffix(".png"))
                    file_type = "png"
                except Exception as e:
                    return AIPassportResult(
                        passport_data=PassportData(),
                        success=False,
                        error_message=f"Failed to convert PDF to image for AI parsing: {e}",
                    )

            if file_type and file_type not in self.VISION_IMAGE_TYPES:
                return AIPassportResult(
                    passport_data=PassportData(),
                    success=False,
                    error_message=(
                        f"Unsupported file type: {file_type}. " f"Supported: {', '.join(self.SUPPORTED_TYPES)}"
                    ),
                )

            logger.info(f"AI parsing passport image: {filename} " f"(type: {file_type}, model: {self.ai_client.model})")

            return self._parse_with_vision(file_bytes, filename)

        except Exception as e:
            return AIPassportResult(
                passport_data=PassportData(),
                success=False,
                error_message=str(e),
            )

    def _parse_with_vision(self, image_bytes: bytes, filename: str) -> AIPassportResult:
        """Parse passport image using vision capabilities with validation and retry."""
        try:
            # Initial attempt
            prompt = self._build_vision_prompt()
            result = self._call_vision_api(image_bytes, filename, prompt)

            if not result.success:
                return result

            # Validate passport number
            passport_number = result.passport_data.passport_number
            is_valid, validation_msg = validate_passport_number_icao(passport_number)

            if is_valid:
                logger.info(f"Passport number validated: {passport_number}")
                return result

            # Passport number validation failed - retry with focused prompt
            logger.warning(f"Passport number validation failed: {validation_msg}. Retrying...")

            last_validation_msg = validation_msg
            for attempt in range(1, self.MAX_PASSPORT_VALIDATION_RETRIES + 1):
                logger.info(f"Retry attempt {attempt}/{self.MAX_PASSPORT_VALIDATION_RETRIES}")

                # Build focused retry prompt
                retry_prompt = self._build_retry_prompt(passport_number, validation_msg)
                retry_result = self._call_vision_api(image_bytes, filename, retry_prompt)

                if not retry_result.success:
                    continue

                # Validate the new passport number
                new_passport_number = retry_result.passport_data.passport_number
                is_valid, last_validation_msg = validate_passport_number_icao(new_passport_number)

                if is_valid:
                    logger.info(f"Passport number validated on retry: {new_passport_number}")
                    return retry_result

                logger.warning(f"Retry {attempt} failed validation: {last_validation_msg}")
                passport_number = new_passport_number  # Use latest for next retry prompt

            # All retries exhausted - return failure with error message
            error_message = (
                f"Passport number validation failed after {self.MAX_PASSPORT_VALIDATION_RETRIES} retries. "
                f"Last extracted value '{passport_number}' is invalid: {last_validation_msg}"
            )
            logger.error(error_message)
            return AIPassportResult(
                passport_data=PassportData(),
                success=False,
                error_message=error_message,
            )

        except Exception as e:
            return AIPassportResult(
                passport_data=PassportData(),
                success=False,
                error_message=str(e),
            )

    def _call_vision_api(self, image_bytes: bytes, filename: str, prompt: str) -> AIPassportResult:
        """Make a single vision API call and return the result."""
        try:
            messages = self.ai_client.build_vision_message(
                prompt=prompt,
                image_bytes=image_bytes,
                filename=filename,
                system_prompt=self.SYSTEM_PROMPT,
            )

            logger.info(f"Sending passport image to {self.ai_client.provider_name} vision API")

            parsed_data = self.ai_client.chat_completion_json(
                messages=messages,
                json_schema=self.PASSPORT_SCHEMA,
                schema_name="passport_data",
            )

            logger.info("Successfully parsed passport data from vision API")
            return self._convert_to_result(parsed_data)

        except Exception as e:
            # error_message will contain the detailed message from AIClient
            return AIPassportResult(
                passport_data=PassportData(),
                success=False,
                error_message=str(e),
            )

    def _build_retry_prompt(self, invalid_passport_number: str, validation_error: str) -> str:
        """Build a focused retry prompt when passport number validation fails."""
        base_prompt = self._build_vision_prompt()

        retry_addition = f"""
IMPORTANT: Previous extraction returned an INVALID passport number: "{invalid_passport_number}"
Error: {validation_error}

Please carefully re-read the passport number from the document.
- Look at the "Passport No." or "Document No." field on the passport
- The passport number is typically 8-9 alphanumeric characters
- Do NOT include MRZ (machine readable zone) data at the bottom of the passport
- Do NOT concatenate multiple fields together
- Copy ONLY the passport number exactly as shown in the visual zone

"""
        return retry_addition + base_prompt

    def _build_vision_prompt(self) -> str:
        """
        Build prompt for vision API passport analysis.
        Simplified for cheap AI models like gemini-flash-lite.
        """
        return """Extract passport data from this image. Return JSON.

RULES:
1. NAMES: Format as title case - first letter of each word capital, rest lowercase. Names can be multiple words (e.g., "John Paul", "Stefano Giulio Mario"). Capitalize each word in the name.
2. DATES: Always use YYYY-MM-DD format (example: 1986-12-19)
3. NATIONALITY: Use 3-letter code like ITA, USA, DEU, FRA, GBR
4. GENDER: Use M or F
5. EYE COLOR: Translate to English (Brown, Blue, Green, Hazel, Gray, Black)
6. ISSUING COUNTRY: Use English name (Italy, Germany, France)
7. If field not visible: use null

FIELDS TO EXTRACT:
- first_name: given name(s) (title case, can be multiple words)
- last_name: family name(s) (title case, can be multiple words)
- full_name: complete name (title case, first + last)
- nationality: 3-letter country code (ITA, USA, etc)
- nationality_code: same 3-letter code
- gender: M or F
- date_of_birth: YYYY-MM-DD
- birth_place: city as shown on passport
- passport_number: document number (copy exactly)
- passport_issue_date: YYYY-MM-DD
- passport_expiration_date: YYYY-MM-DD
- issuing_country: country name in English
- issuing_country_code: 3-letter code
- issuing_authority: authority name as shown
- height_cm: height in cm (integer)
- eye_color: in English (Brown, Blue, Green, etc)
- address_abroad: address if visible, else null
- document_type: usually P for passport
- confidence_score: 0.0 to 1.0 (how clear is the image)

EXAMPLE OUTPUT:
{
  "first_name": "Mario Luigi",
  "last_name": "Rossi Bianchi",
  "full_name": "Mario Luigi Rossi Bianchi",
  "nationality": "ITA",
  "nationality_code": "ITA",
  "gender": "M",
  "date_of_birth": "1985-03-15",
  "birth_place": "Roma",
  "passport_number": "YA1234567",
  "passport_issue_date": "2020-01-10",
  "passport_expiration_date": "2030-01-09",
  "issuing_country": "Italy",
  "issuing_country_code": "ITA",
  "issuing_authority": "MINISTERO DELL'INTERNO",
  "height_cm": 175,
  "eye_color": "Brown",
  "address_abroad": null,
  "document_type": "P",
  "confidence_score": 0.95
}
"""

    def _convert_to_result(self, parsed_data: dict) -> AIPassportResult:
        """Convert parsed JSON data to structured result objects."""
        # Log the raw parsed JSON returned by the vision API for debugging
        try:
            logger.info("AI parsed passport data: %s", json.dumps(parsed_data, ensure_ascii=False, default=str))
        except Exception:
            logger.debug("Failed to stringify AI parsed passport data for logging.")
        passport_data = PassportData(
            first_name=parsed_data.get("first_name"),
            last_name=parsed_data.get("last_name"),
            full_name=parsed_data.get("full_name"),
            nationality=parsed_data.get("nationality"),
            nationality_code=parsed_data.get("nationality_code"),
            gender=parsed_data.get("gender"),
            date_of_birth=parsed_data.get("date_of_birth"),
            birth_place=parsed_data.get("birth_place"),
            passport_number=parsed_data.get("passport_number"),
            passport_issue_date=parsed_data.get("passport_issue_date"),
            passport_expiration_date=parsed_data.get("passport_expiration_date"),
            issuing_country=parsed_data.get("issuing_country"),
            issuing_country_code=parsed_data.get("issuing_country_code"),
            issuing_authority=parsed_data.get("issuing_authority"),
            height_cm=parsed_data.get("height_cm"),
            eye_color=parsed_data.get("eye_color"),
            address_abroad=parsed_data.get("address_abroad"),
            document_type=parsed_data.get("document_type"),
            confidence_score=float(parsed_data.get("confidence_score", 0.0)),
        )

        return AIPassportResult(
            passport_data=passport_data,
            raw_response=parsed_data,
            success=True,
            error_message=None,
        )
