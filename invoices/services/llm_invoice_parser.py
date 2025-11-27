"""
LLM Invoice Parser - Backward Compatibility Module

This module re-exports the AI Invoice Parser from core.services for backward compatibility.
New code should import directly from core.services:

    from core.services import AIInvoiceParser, ParsedInvoiceResult

Deprecated imports (still work but will show deprecation warning):
    from invoices.services.llm_invoice_parser import LLMInvoiceParser
"""

import warnings

# Re-export from core.services
from core.services.ai_invoice_parser import (
    AIInvoiceParser,
    CustomerData,
    InvoiceData,
    InvoiceLineItemData,
    ParsedInvoiceResult,
)


# Backward compatibility alias with deprecation warning
class LLMInvoiceParser(AIInvoiceParser):
    """
    Backward compatibility wrapper for LLMInvoiceParser.

    .. deprecated::
        Use `core.services.AIInvoiceParser` instead.
    """

    def __init__(self, *args, **kwargs):
        warnings.warn(
            "LLMInvoiceParser is deprecated. Use core.services.AIInvoiceParser instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)


__all__ = [
    "AIInvoiceParser",
    "LLMInvoiceParser",  # Deprecated
    "CustomerData",
    "InvoiceData",
    "InvoiceLineItemData",
    "ParsedInvoiceResult",
]
