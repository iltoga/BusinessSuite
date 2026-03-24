"""Phone Number document type hook."""

from typing import TYPE_CHECKING

from core.services.logger_service import Logger

from .base import BaseDocumentTypeHook

if TYPE_CHECKING:
    from customer_applications.models import Document

logger = Logger.get_logger(__name__)


class PhoneNumberHook(BaseDocumentTypeHook):
    """Hook for Phone Number document type.
    
    Pre-fills the document details with the customer's telephone or whatsapp on creation.
    Updates the customer's telephone if the document details are modified.
    """

    document_type_name = "Phone Number"

    def on_pre_save(self, document: "Document", created: bool) -> None:
        if created:
            customer = document.doc_application.customer
            val = customer.telephone or customer.whatsapp or ""
            if val and not document.details:
                document.details = val

    def on_post_save(self, document: "Document", created: bool) -> None:
        if not created:
            customer = document.doc_application.customer
            update_fields = []
            
            if customer.telephone != document.details:
                customer.telephone = document.details
                update_fields.append("telephone")

            if customer.whatsapp and customer.whatsapp != document.details:
                customer.whatsapp = document.details
                update_fields.append("whatsapp")

            if update_fields:
                update_fields.append("updated_at")
                customer.save(update_fields=update_fields)
                logger.info(
                    "Updated Customer %s fields %s from Document %s",
                    customer.pk,
                    update_fields,
                    document.pk,
                )
