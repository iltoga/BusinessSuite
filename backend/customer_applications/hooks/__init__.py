"""Document type hooks system.

This module provides a pluggable architecture for adding document-type-specific
behaviors to the Document model lifecycle.
"""

from .base import BaseDocumentTypeHook, DocumentAction
from .ktp_sponsor import PassportSponsorHook
from .registry import HookRegistry, hook_registry
from .surat_permohonan import SuratPermohonanHook
from .address import AddressHook
from .phone_number import PhoneNumberHook

__all__ = [
    "BaseDocumentTypeHook",
    "DocumentAction",
    "HookRegistry",
    "hook_registry",
    "PassportSponsorHook",
    "SuratPermohonanHook",
    "AddressHook",
    "PhoneNumberHook",
]

# Register hooks
hook_registry.register(PassportSponsorHook())
hook_registry.register(SuratPermohonanHook())
hook_registry.register(AddressHook())
hook_registry.register(PhoneNumberHook())
