"""Address document type hook."""

from typing import TYPE_CHECKING

from core.services.logger_service import Logger

from .base import BaseDocumentTypeHook

if TYPE_CHECKING:
    from customer_applications.models import Document

logger = Logger.get_logger(__name__)


class AddressHook(BaseDocumentTypeHook):
    """Hook for Address document type.
    
    Pre-fills the document details with the customer's Bali address on creation.
    Updates the customer's Bali address if the document details are modified.
    """

    document_type_name = "Address"

    def on_pre_save(self, document: "Document", created: bool) -> None:
        if created:
            customer = document.doc_application.customer
            val = customer.address_bali or ""
            if val and not document.details:
                document.details = val

    def on_post_save(self, document: "Document", created: bool) -> None:
        if not created:
            customer = document.doc_application.customer
            if customer.address_bali != document.details:
                customer.address_bali = document.details
                customer.save(update_fields=["address_bali", "updated_at"])
                logger.info(
                    "Updated Customer %s address_bali from Document %s",
                    customer.pk,
                    document.pk,
                )
