"""
LLM Invoice Parser Service
Uses OpenRouter API (with OpenAI GPT-5-mini or other models) to extract structured invoice data from documents.
Supports multimodal vision for PDF/images and text extraction for Excel/Word documents.
"""

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Union

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class InvoiceLineItemData:
    """Structured data for a single invoice line item."""

    code: str
    description: str
    quantity: float
    unit_price: float
    amount: float


@dataclass
class CustomerData:
    """Structured data for customer information."""

    full_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None


@dataclass
class InvoiceData:
    """Structured data for invoice information."""

    invoice_no: str
    invoice_date: str  # ISO format: YYYY-MM-DD
    due_date: str  # ISO format: YYYY-MM-DD
    total_amount: float
    notes: Optional[str] = None
    payment_status: Optional[str] = None
    bank_details: Optional[dict] = None


@dataclass
class ParsedInvoiceResult:
    """Complete parsed invoice result."""

    customer: CustomerData
    invoice: InvoiceData
    line_items: List[InvoiceLineItemData]
    confidence_score: float  # 0-1 scale
    raw_response: dict


class LLMInvoiceParser:
    """
    Service to parse invoices using OpenRouter API with multimodal vision models.
    Supports direct PDF and image processing without OCR preprocessing.
    Uses OpenAI-compatible API through OpenRouter for flexible model selection.
    """

    # JSON Schema for structured output
    INVOICE_SCHEMA = {
        "type": "object",
        "properties": {
            "customer": {
                "type": "object",
                "properties": {
                    "full_name": {"type": "string"},
                    "first_name": {"type": ["string", "null"]},
                    "last_name": {"type": ["string", "null"]},
                    "email": {"type": ["string", "null"]},
                    "phone": {"type": ["string", "null"]},
                    "mobile_phone": {"type": ["string", "null"]},
                },
                "required": ["full_name", "first_name", "last_name", "email", "phone", "mobile_phone"],
                "additionalProperties": False,
            },
            "invoice": {
                "type": "object",
                "properties": {
                    "invoice_no": {"type": "string"},
                    "invoice_date": {"type": "string"},
                    "due_date": {"type": "string"},
                    "total_amount": {"type": "number"},
                    "notes": {"type": ["string", "null"]},
                    "payment_status": {"type": ["string", "null"]},
                    "bank_details": {
                        "type": ["object", "null"],
                        "properties": {
                            "bank_name": {"type": ["string", "null"]},
                            "beneficiary_name": {"type": ["string", "null"]},
                            "account_number": {"type": ["string", "null"]},
                            "branch": {"type": ["string", "null"]},
                            "address": {"type": ["string", "null"]},
                            "bic_swift": {"type": ["string", "null"]},
                            "email": {"type": ["string", "null"]},
                        },
                        "required": [
                            "bank_name",
                            "beneficiary_name",
                            "account_number",
                            "branch",
                            "address",
                            "bic_swift",
                            "email",
                        ],
                        "additionalProperties": False,
                    },
                },
                "required": [
                    "invoice_no",
                    "invoice_date",
                    "due_date",
                    "total_amount",
                    "notes",
                    "payment_status",
                    "bank_details",
                ],
                "additionalProperties": False,
            },
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "description": {"type": "string"},
                        "quantity": {"type": "number"},
                        "unit_price": {"type": "number"},
                        "amount": {"type": "number"},
                    },
                    "required": ["code", "description", "quantity", "unit_price", "amount"],
                    "additionalProperties": False,
                },
            },
            "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["customer", "invoice", "line_items", "confidence_score"],
        "additionalProperties": False,
    }

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, use_openrouter: bool = True):
        """
        Initialize the parser with OpenRouter or OpenAI API.

        Args:
            api_key: API key (defaults to settings.OPENROUTER_API_KEY or OPENAI_API_KEY)
            model: Model to use (default: from settings or 'openai/gpt-5-mini' for OpenRouter)
            use_openrouter: Whether to use OpenRouter (default: True)
        """
        self.use_openrouter = use_openrouter

        if use_openrouter:
            self.api_key = api_key or getattr(settings, "OPENROUTER_API_KEY", None)
            if not self.api_key:
                raise ValueError("OpenRouter API key not configured. Set OPENROUTER_API_KEY in settings or .env file.")

            # OpenRouter uses 'provider/model' format
            default_model = getattr(settings, "LLM_DEFAULT_MODEL", "google/gemini-2.0-flash-001")
            self.model = model or default_model

            # Initialize OpenAI client with OpenRouter base URL and timeout
            base_url = getattr(settings, "OPENROUTER_API_BASE_URL", "https://openrouter.ai/api/v1")
            # Set a generous timeout for LLM API calls (vision models can take 60-120 seconds)
            timeout = getattr(settings, "OPENROUTER_TIMEOUT", 120.0)

            self.client = OpenAI(
                api_key=self.api_key,
                base_url=base_url,
                timeout=timeout,
            )
            logger.info(f"Initialized LLM parser with OpenRouter (model: {self.model}, timeout: {timeout}s)")
        else:
            self.api_key = api_key or getattr(settings, "OPENAI_API_KEY", None)
            if not self.api_key:
                raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in settings or .env file.")

            self.model = model or getattr(settings, "LLM_DEFAULT_MODEL", "gpt-4o-mini")
            # Set a generous timeout for LLM API calls
            timeout = getattr(settings, "OPENAI_TIMEOUT", 120.0)

            self.client = OpenAI(
                api_key=self.api_key,
                timeout=timeout,
            )
            logger.info(f"Initialized LLM parser with OpenAI (model: {self.model}, timeout: {timeout}s)")

    def parse_invoice_file(
        self, file_content: Union[bytes, UploadedFile], filename: str = "", file_type: str = ""
    ) -> Optional[ParsedInvoiceResult]:
        """
        Parse invoice file using multimodal vision (PDF, images) or structured data extraction (Excel, Word).

        Args:
            file_content: File bytes or Django UploadedFile
            filename: Original filename for context
            file_type: File extension (pdf, png, jpg, xlsx, docx, etc.)

        Returns:
            ParsedInvoiceResult or None if parsing fails
        """
        try:
            # Handle UploadedFile
            if isinstance(file_content, UploadedFile):
                file_content.seek(0)
                file_bytes = file_content.read()
                filename = filename or file_content.name
            else:
                file_bytes = file_content

            # Detect file type if not provided
            if not file_type and filename:
                file_type = Path(filename).suffix.lower().lstrip(".")

            logger.info(f"Parsing invoice file: {filename} (type: {file_type}, model: {self.model})")

            # For PDF and images, use multimodal vision
            if file_type in ["pdf", "png", "jpg", "jpeg", "gif", "webp"]:
                return self._parse_with_vision(file_bytes, filename, file_type)

            # For Excel and Word, extract text first then use vision on text
            elif file_type in ["xlsx", "xls", "docx", "doc"]:
                return self._parse_structured_document(file_bytes, filename, file_type)

            else:
                logger.error(f"Unsupported file type: {file_type}")
                return None

        except Exception as e:
            logger.error(f"Error parsing invoice file: {str(e)}")
            return None

    def _parse_with_vision(self, file_bytes: bytes, filename: str, file_type: str) -> Optional[ParsedInvoiceResult]:
        """
        Parse PDF or image using GPT-5-mini vision capabilities.
        """
        try:
            # For PDF, we need to convert to images first (GPT vision accepts images, not raw PDFs)
            if file_type == "pdf":
                # Import here to avoid dependency issues if not needed
                from pdf2image import convert_from_bytes

                images = convert_from_bytes(file_bytes, dpi=200, fmt="png")
                # Use first page for now (could extend to multi-page)
                img_byte_arr = BytesIO()
                images[0].save(img_byte_arr, format="PNG")
                image_bytes = img_byte_arr.getvalue()
            else:
                image_bytes = file_bytes

            # Encode image to base64
            base64_image = base64.b64encode(image_bytes).decode("utf-8")

            # Build messages with image content
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert at extracting structured data from invoice documents. "
                    "Analyze the invoice image carefully and extract all relevant information.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._build_vision_prompt(filename)},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                    ],
                },
            ]

            provider = "OpenRouter" if self.use_openrouter else "OpenAI"
            logger.info(f"Sending invoice image to {provider} vision API (model: {self.model})")

            # Call API with structured output
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "invoice_data",
                        "schema": self.INVOICE_SCHEMA,
                        "strict": True,
                    },
                },
            )

            # Parse response
            response_text = response.choices[0].message.content
            parsed_data = json.loads(response_text)

            logger.info("Successfully parsed invoice data from vision API")

            return self._convert_to_result(parsed_data)

        except Exception as e:
            logger.error(f"Error in vision parsing: {str(e)}")
            return None

    def _parse_structured_document(
        self, file_bytes: bytes, filename: str, file_type: str
    ) -> Optional[ParsedInvoiceResult]:
        """
        Parse Excel or Word documents by extracting text then using LLM.
        """
        try:
            # Extract text using appropriate library
            if file_type in ["xlsx", "xls"]:
                from datetime import datetime as dt

                import openpyxl

                # Use data_only=True to get calculated values instead of formulas
                workbook = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True)
                sheet = workbook.active
                text_parts = []

                for row in sheet.iter_rows(values_only=True):
                    formatted_cells = []
                    for cell in row:
                        if cell is None:
                            formatted_cells.append("")
                        elif isinstance(cell, dt):
                            # Format datetime objects as YYYY-MM-DD
                            formatted_cells.append(cell.strftime("%Y-%m-%d"))
                        elif isinstance(cell, (int, float)):
                            # Keep numbers as is (no formatting to preserve precision)
                            formatted_cells.append(str(cell))
                        else:
                            formatted_cells.append(str(cell))

                    row_text = " | ".join(formatted_cells)
                    if row_text.strip():
                        text_parts.append(row_text)

                text = "\n".join(text_parts)

            elif file_type in ["docx", "doc"]:
                from docx import Document

                doc = Document(BytesIO(file_bytes))
                text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])

            else:
                logger.error(f"Unsupported structured document type: {file_type}")
                return None

            # Now use LLM to parse the text with structured output
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert at extracting structured data from invoice documents.",
                },
                {"role": "user", "content": self._build_text_prompt(text, filename)},
            ]

            provider = "OpenRouter" if self.use_openrouter else "OpenAI"
            logger.info(f"Sending extracted text to {provider} (model: {self.model})")

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "invoice_data",
                        "schema": self.INVOICE_SCHEMA,
                        "strict": True,
                    },
                },
            )

            response_text = response.choices[0].message.content
            parsed_data = json.loads(response_text)

            logger.info("Successfully parsed invoice data from structured document")

            return self._convert_to_result(parsed_data)

        except Exception as e:
            logger.error(f"Error parsing structured document: {str(e)}")
            return None

    def _build_vision_prompt(self, filename: str) -> str:
        """
        Build prompt for vision API (image/PDF analysis).
        """
        prompt = f"""Analyze this invoice document (file: {filename}) and extract all structured data.

IMPORTANT EXTRACTION RULES:

1. Extract ALL line items/services listed
2. Convert dates to YYYY-MM-DD format (e.g., "10/29/2025" → "2025-10-29", "29 Oct 2025" → "2025-10-29")
3. Remove currency symbols and formatting from amounts (e.g., "Rp 16,250,000" → 16250000.00)
4. For invoice_no, extract only numeric part (e.g., "INV-202634" → "202634")
5. Split customer full_name into first_name and last_name
6. If due_date not specified, use same as invoice_date
7. confidence_score: 0.9+ if clear, 0.5-0.8 if partially unclear, <0.5 if very uncertain
8. For missing optional fields, use null

Look carefully at the document for:
- Customer name and contact info
- Invoice number and dates
- Line items with codes, descriptions, quantities, prices
- Total amount
- Bank details and payment info
"""
        return prompt

    def _build_text_prompt(self, text: str, filename: str) -> str:
        """
        Build prompt for text-based parsing (Excel/Word extracted text).
        """
        prompt = f"""Extract structured invoice data from the following text (file: {filename}).

INVOICE TEXT:
---
{text}
---

{self._build_vision_prompt(filename)}
"""
        return prompt

    def _convert_to_result(self, parsed_data: dict) -> ParsedInvoiceResult:
        """
        Convert parsed JSON data to structured result objects.
        """
        # Extract customer data
        customer_dict = parsed_data.get("customer", {})
        customer = CustomerData(
            full_name=customer_dict.get("full_name", ""),
            first_name=customer_dict.get("first_name"),
            last_name=customer_dict.get("last_name"),
            email=customer_dict.get("email"),
            phone=customer_dict.get("phone"),
            mobile_phone=customer_dict.get("mobile_phone"),
        )

        # Extract invoice data
        invoice_dict = parsed_data.get("invoice", {})
        invoice = InvoiceData(
            invoice_no=str(invoice_dict.get("invoice_no", "")),
            invoice_date=invoice_dict.get("invoice_date", ""),
            due_date=invoice_dict.get("due_date", ""),
            total_amount=float(invoice_dict.get("total_amount", 0)),
            notes=invoice_dict.get("notes"),
            payment_status=invoice_dict.get("payment_status"),
            bank_details=invoice_dict.get("bank_details"),
        )

        # Extract line items
        line_items = []
        for item_dict in parsed_data.get("line_items", []):
            line_item = InvoiceLineItemData(
                code=item_dict.get("code", ""),
                description=item_dict.get("description", ""),
                quantity=float(item_dict.get("quantity", 1)),
                unit_price=float(item_dict.get("unit_price", 0)),
                amount=float(item_dict.get("amount", 0)),
            )
            line_items.append(line_item)

        confidence_score = float(parsed_data.get("confidence_score", 0.5))

        return ParsedInvoiceResult(
            customer=customer,
            invoice=invoice,
            line_items=line_items,
            confidence_score=confidence_score,
            raw_response=parsed_data,
        )

    def validate_parsed_data(self, result: ParsedInvoiceResult) -> tuple[bool, list[str]]:
        """
        Validate parsed data for completeness and consistency.

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        # Validate customer
        if not result.customer.full_name:
            errors.append("Customer name is missing")

        # Validate invoice
        if not result.invoice.invoice_no:
            errors.append("Invoice number is missing")

        if not result.invoice.invoice_date:
            errors.append("Invoice date is missing")
        else:
            try:
                datetime.strptime(result.invoice.invoice_date, "%Y-%m-%d")
            except ValueError:
                errors.append(f"Invalid invoice date format: {result.invoice.invoice_date}")

        if not result.invoice.due_date:
            errors.append("Due date is missing")
        else:
            try:
                datetime.strptime(result.invoice.due_date, "%Y-%m-%d")
            except ValueError:
                errors.append(f"Invalid due date format: {result.invoice.due_date}")

        if result.invoice.total_amount <= 0:
            errors.append("Total amount must be greater than 0")

        # Validate line items
        if not result.line_items:
            errors.append("No line items found")
        else:
            for i, item in enumerate(result.line_items):
                if not item.description:
                    errors.append(f"Line item {i+1}: description is missing")
                if item.amount <= 0:
                    errors.append(f"Line item {i+1}: amount must be greater than 0")

        # Validate total matches sum of line items
        if result.line_items:
            line_items_total = sum(item.amount for item in result.line_items)
            if abs(line_items_total - result.invoice.total_amount) > 0.01:  # Allow small floating point differences
                errors.append(
                    f"Total amount mismatch: invoice total {result.invoice.total_amount} != line items total {line_items_total}"
                )

        # Check confidence score
        if result.confidence_score < 0.5:
            errors.append(f"Low confidence score: {result.confidence_score:.2f}")

        return len(errors) == 0, errors
