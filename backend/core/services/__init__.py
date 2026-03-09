"""
Core service exports with lazy imports.

This module intentionally avoids importing heavy service modules at import time
because some callers import `core.services.<module>` before `django.setup()`
(for example Dramatiq bootstrap telemetry middleware).
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

_EXPORT_MAP = {
    # AI client + usage
    "AIClient": ("core.services.ai_client", "AIClient"),
    "AIUsageService": ("core.services.ai_usage_service", "AIUsageService"),
    "AIUsageFeature": ("core.services.ai_usage_service", "AIUsageFeature"),
    # Passport parser
    "AIPassportParser": ("core.services.ai_passport_parser", "AIPassportParser"),
    "AIPassportResult": ("core.services.ai_passport_parser", "AIPassportResult"),
    "PassportData": ("core.services.ai_passport_parser", "PassportData"),
    # Invoice parser
    "AIInvoiceParser": ("core.services.ai_invoice_parser", "AIInvoiceParser"),
    "LLMInvoiceParser": ("core.services.ai_invoice_parser", "LLMInvoiceParser"),
    "CustomerData": ("core.services.ai_invoice_parser", "CustomerData"),
    "InvoiceData": ("core.services.ai_invoice_parser", "InvoiceData"),
    "InvoiceLineItemData": ("core.services.ai_invoice_parser", "InvoiceLineItemData"),
    "ParsedInvoiceResult": ("core.services.ai_invoice_parser", "ParsedInvoiceResult"),
}

if TYPE_CHECKING:
    from core.services.ai_client import AIClient
    from core.services.ai_invoice_parser import (
        AIInvoiceParser,
        CustomerData,
        InvoiceData,
        InvoiceLineItemData,
        LLMInvoiceParser,
        ParsedInvoiceResult,
    )
    from core.services.ai_passport_parser import AIPassportParser, AIPassportResult, PassportData
    from core.services.ai_usage_service import AIUsageFeature, AIUsageService

__all__ = (
    "AIClient",
    "AIUsageService",
    "AIUsageFeature",
    "AIPassportParser",
    "AIPassportResult",
    "PassportData",
    "AIInvoiceParser",
    "LLMInvoiceParser",
    "CustomerData",
    "InvoiceData",
    "InvoiceLineItemData",
    "ParsedInvoiceResult",
)


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _EXPORT_MAP[name]
    except KeyError as exc:
        raise AttributeError(f"module 'core.services' has no attribute {name!r}") from exc
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
