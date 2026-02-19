"""
Core AI Services
================

This module provides reusable AI-powered services for the application.

Available Services:
- AIClient: Base client for OpenRouter/OpenAI API access
- AIPassportParser: Extract structured data from passport images
- AIInvoiceParser: Extract structured data from invoice documents

Usage:
    from core.services import AIClient, AIPassportParser, AIInvoiceParser

    # Use base client for custom AI operations
    client = AIClient()
    response = client.chat_completion(messages=[...])

    # Parse passport images
    parser = AIPassportParser()
    result = parser.parse_passport_image(file_content)

    # Parse invoice documents
    parser = AIInvoiceParser()
    result = parser.parse_invoice_file(file_content)
"""

from core.services.ai_client import AIClient
from core.services.ai_invoice_parser import LLMInvoiceParser  # Backward compatibility alias
from core.services.ai_invoice_parser import (
    AIInvoiceParser,
    CustomerData,
    InvoiceData,
    InvoiceLineItemData,
    ParsedInvoiceResult,
)
from core.services.ai_usage_service import AIUsageFeature, AIUsageService
from core.services.ai_passport_parser import AIPassportParser, AIPassportResult, PassportData

__all__ = [
    # Base client
    "AIClient",
    "AIUsageService",
    "AIUsageFeature",
    # Passport parser
    "AIPassportParser",
    "AIPassportResult",
    "PassportData",
    # Invoice parser
    "AIInvoiceParser",
    "LLMInvoiceParser",  # Backward compatibility
    "CustomerData",
    "InvoiceData",
    "InvoiceLineItemData",
    "ParsedInvoiceResult",
]
