"""Surat Permohonan dan Jaminan document type hook.

This hook provides auto-generation capability for Surat Permohonan documents
using the existing LetterService. The generated DOCX is converted to PDF
before being saved to the document.
"""

from typing import TYPE_CHECKING, Any, Dict, List

from django.core.files.base import ContentFile

from core.utils.pdf_converter import PDFConverter, PDFConverterError

from .base import BaseDocumentTypeHook, DocumentAction

if TYPE_CHECKING:
    from django.http import HttpRequest

    from customer_applications.models import Document

from core.services.logger_service import Logger

logger = Logger.get_logger(__name__)


class SuratPermohonanHook(BaseDocumentTypeHook):
    """Hook for Surat Permohonan dan Jaminan document type.

    Provides an auto-generate action that creates the Surat Permohonan document
    using customer and application data via the LetterService.
    """

    document_type_name = "Surat Permohonan dan Jaminan"

    @staticmethod
    def _safe_file_path_for_logging(document: "Document") -> str:
        """Return file path when backend supports it, otherwise a safe placeholder."""
        if not document.file:
            return "N/A"

        try:
            return document.file.path
        except (AttributeError, NotImplementedError, ValueError):
            return "N/A"

    def get_extra_actions(self) -> List[DocumentAction]:
        """Returns the auto-generate action for this document type."""
        return [
            DocumentAction(
                name="auto_generate",
                label="Auto Generate",
                icon="fas fa-magic",
                css_class="btn-success",
            )
        ]

    def execute_action(self, action_name: str, document: "Document", request: "HttpRequest") -> Dict[str, Any]:
        """Execute a named action on the document.

        Args:
            action_name: The name of the action to execute.
            document: The Document instance to act on.
            request: The HTTP request object.

        Returns:
            A dict with 'success' boolean and either 'message' or 'error'.
        """
        if action_name == "auto_generate":
            return self._generate_surat(document, request)
        return {"success": False, "error": "Unknown action"}

    def _generate_surat(self, document: "Document", request: "HttpRequest") -> Dict[str, Any]:
        """Generate the Surat Permohonan document as PDF.

        Generates a DOCX using LetterService, converts it to PDF using
        LibreOffice (via PDFConverter), and saves the PDF to the document.

        Args:
            document: The Document instance to generate the file for.
            request: The HTTP request object.

        Returns:
            A dict with 'success' boolean and either 'message' or 'error'.
        """
        try:
            # Import here to avoid circular imports
            from letters.services.LetterService import LetterService

            customer = document.doc_application.customer

            # Check if customer has Bali address populated
            if not customer.address_bali or not customer.address_bali.strip():
                logger.warning(
                    "Cannot generate Surat Permohonan: customer %s has no Bali address",
                    customer.pk,
                )
                return {
                    "success": False,
                    "error": "Cannot generate document: Customer does not have a Bali address populated. Please update the customer's Bali address first.",
                }

            # Generate the DOCX document
            service = LetterService(customer)
            data = service.generate_letter_data()
            doc_buffer = service.generate_letter_document(data)

            # Convert DOCX to PDF
            try:
                pdf_bytes = PDFConverter.docx_buffer_to_pdf(doc_buffer)
                logger.info(
                    "PDF conversion successful, size: %d bytes (customer %s)",
                    len(pdf_bytes),
                    customer.pk,
                )
            except PDFConverterError as e:
                logger.error(
                    "PDF conversion failed for Surat Permohonan (customer %s): %s",
                    customer.pk,
                    str(e),
                )
                return {
                    "success": False,
                    "error": f"PDF conversion failed: {str(e)}. Please ensure LibreOffice is installed.",
                }

            # Validate PDF bytes
            if not pdf_bytes or len(pdf_bytes) == 0:
                logger.error("PDF conversion returned empty bytes (customer %s)", customer.pk)
                return {"success": False, "error": "PDF conversion returned empty file"}

            # Save the PDF to the document
            filename = f"surat_permohonan_{customer.pk}.pdf"
            document.file.save(filename, ContentFile(pdf_bytes), save=True)

            # Verify the file was saved
            logger.info(
                "File save completed. document.file.name=%s, document.file.path=%s",
                document.file.name if document.file else "None",
                self._safe_file_path_for_logging(document),
            )

            logger.info(
                "Generated Surat Permohonan PDF for customer %s (document %s)",
                customer.pk,
                document.pk,
            )

            return {"success": True, "message": "Document generated successfully"}
        except FileNotFoundError as e:
            logger.error("Template not found for Surat Permohonan: %s", str(e))
            return {"success": False, "error": f"Template not found: {str(e)}"}
        except Exception as e:
            logger.error("Failed to generate Surat Permohonan: %s", str(e))
            return {"success": False, "error": str(e)}
