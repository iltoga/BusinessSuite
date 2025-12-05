"""Document type hooks system.

This module provides a pluggable architecture for adding document-type-specific
behaviors to the Document model lifecycle.
"""

from .base import BaseDocumentTypeHook, DocumentAction
from .registry import HookRegistry, hook_registry
from .passport_sponsor import PassportSponsorHook
from .surat_permohonan import SuratPermohonanHook

__all__ = [
    "BaseDocumentTypeHook",
    "DocumentAction",
    "HookRegistry",
    "hook_registry",
    "PassportSponsorHook",
    "SuratPermohonanHook",
]

# Register hooks
hook_registry.register(PassportSponsorHook())
hook_registry.register(SuratPermohonanHook())
