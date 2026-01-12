"""
Document Merger Service
=======================

Service for converting multiple documents to PDF and merging them into a single file.
Supports PDF, DOCX, and common image formats.

Usage Example
-------------
    from core.services.document_merger import DocumentMerger

    # Merge documents by file paths
    pdf_bytes = DocumentMerger.merge_documents(['/path/to/doc1.pdf', '/path/to/image.jpg'])

    # Merge Document model instances
    from customer_applications.models import Document
    documents = Document.objects.filter(pk__in=[1, 2, 3])
    pdf_bytes = DocumentMerger.merge_document_models(documents)
"""

import logging
import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Union

from django.core.files.storage import default_storage

from core.utils.pdf_converter import PDFConverter, PDFConverterError

logger = logging.getLogger(__name__)


class DocumentMergerError(Exception):
    """Custom exception for document merger errors."""

    pass


class DocumentMerger:
    """
    Service for merging multiple documents into a single PDF.

    Supports:
    - PDF files (passed through or merged directly)
    - DOCX/DOC files (converted via LibreOffice)
    - Images: JPEG, PNG, TIFF, BMP, GIF, WEBP (converted via Pillow)
    """

    # File extensions that are already PDF
    PDF_EXTENSIONS = {".pdf"}

    # All supported extensions
    SUPPORTED_EXTENSIONS = PDFConverter.IMAGE_EXTENSIONS | PDFConverter.DOCX_EXTENSIONS | PDF_EXTENSIONS

    @classmethod
    def merge_documents(
        cls,
        file_paths: List[Union[str, Path]],
        output_path: Optional[Union[str, Path]] = None,
    ) -> bytes:
        """
        Merge multiple documents into a single PDF.

        Args:
            file_paths: List of paths to documents to merge.
            output_path: Optional path for the output PDF.

        Returns:
            Merged PDF content as bytes.

        Raises:
            DocumentMergerError: If merging fails.
            ValueError: If no valid documents provided.
        """
        if not file_paths:
            raise ValueError("No documents provided for merging.")

        pdf_pages = []

        for file_path in file_paths:
            file_path = Path(file_path)

            if not file_path.exists():
                logger.warning(f"File not found, skipping: {file_path}")
                continue

            ext = file_path.suffix.lower()

            if ext not in cls.SUPPORTED_EXTENSIONS:
                logger.warning(f"Unsupported file format, skipping: {file_path}")
                continue

            try:
                if ext in cls.PDF_EXTENSIONS:
                    # Read PDF directly
                    pdf_bytes = file_path.read_bytes()
                else:
                    # Convert to PDF using PDFConverter
                    pdf_bytes = PDFConverter.convert_to_pdf(file_path)

                pdf_pages.append(pdf_bytes)
                logger.debug(f"Added document to merge: {file_path}")

            except (PDFConverterError, Exception) as e:
                logger.error(f"Failed to process {file_path}: {e}")
                # Continue with other documents
                continue

        if not pdf_pages:
            raise DocumentMergerError("No valid documents could be processed for merging.")

        # Merge all PDFs
        merged_pdf = cls._merge_pdfs(pdf_pages)

        # Write to output file if specified
        if output_path:
            output_path = Path(output_path)
            output_path.write_bytes(merged_pdf)
            logger.info(f"Merged PDF saved to: {output_path}")

        return merged_pdf

    @classmethod
    def merge_document_models(
        cls,
        documents,
        output_path: Optional[Union[str, Path]] = None,
    ) -> bytes:
        """
        Merge Document model instances into a single PDF.

        Args:
            documents: QuerySet or list of Document model instances.
            output_path: Optional path for the output PDF.

        Returns:
            Merged PDF content as bytes.

        Raises:
            DocumentMergerError: If merging fails.
            ValueError: If no valid documents provided.
        """
        if not documents:
            raise ValueError("No documents provided for merging.")

        pdf_pages = []
        temp_files = []

        try:
            for doc in documents:
                # Skip documents without files
                if not doc.file or not doc.file.name:
                    logger.warning(f"Document {doc.pk} has no file, skipping.")
                    continue

                try:
                    # Get the file extension
                    ext = os.path.splitext(doc.file.name)[1].lower()

                    if ext not in cls.SUPPORTED_EXTENSIONS:
                        logger.warning(f"Unsupported file format for document {doc.pk}: {ext}")
                        continue

                    # Read file content from storage
                    file_content = default_storage.open(doc.file.name, "rb").read()

                    if ext in cls.PDF_EXTENSIONS:
                        # PDF - use directly
                        pdf_bytes = file_content
                    elif ext in PDFConverter.IMAGE_EXTENSIONS:
                        # Image - convert to PDF
                        buffer = BytesIO(file_content)
                        pdf_bytes = PDFConverter.image_buffer_to_pdf(buffer)
                    elif ext in PDFConverter.DOCX_EXTENSIONS:
                        # DOCX - need to write to temp file for LibreOffice
                        temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False, prefix="merge_doc_")
                        temp_file.write(file_content)
                        temp_file.close()
                        temp_files.append(temp_file.name)
                        pdf_bytes = PDFConverter.docx_to_pdf(temp_file.name)
                    else:
                        logger.warning(f"Cannot process document {doc.pk} with extension {ext}")
                        continue

                    pdf_pages.append(pdf_bytes)
                    logger.debug(f"Added document {doc.pk} ({doc.doc_type.name}) to merge")

                except Exception as e:
                    logger.error(f"Failed to process document {doc.pk}: {e}")
                    # Continue with other documents
                    continue

            if not pdf_pages:
                raise DocumentMergerError("No valid documents could be processed for merging.")

            # Merge all PDFs
            merged_pdf = cls._merge_pdfs(pdf_pages)

            # Write to output file if specified
            if output_path:
                output_path = Path(output_path)
                output_path.write_bytes(merged_pdf)
                logger.info(f"Merged PDF saved to: {output_path}")

            return merged_pdf

        finally:
            # Cleanup temp files
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass

    @classmethod
    def _merge_pdfs(cls, pdf_bytes_list: List[bytes]) -> bytes:
        """
        Merge multiple PDF byte arrays into a single PDF.

        Args:
            pdf_bytes_list: List of PDF content as bytes.

        Returns:
            Merged PDF content as bytes.
        """
        from pypdf import PdfReader, PdfWriter

        if len(pdf_bytes_list) == 1:
            # Only one PDF, no need to merge
            return pdf_bytes_list[0]

        writer = PdfWriter()

        for pdf_bytes in pdf_bytes_list:
            try:
                reader = PdfReader(BytesIO(pdf_bytes))
                for page in reader.pages:
                    writer.add_page(page)
            except Exception as e:
                logger.error(f"Failed to read PDF for merging: {e}")
                # Continue with other PDFs
                continue

        if len(writer.pages) == 0:
            raise DocumentMergerError("No pages could be extracted from the provided PDFs.")

        # Write merged PDF to buffer
        output_buffer = BytesIO()
        writer.write(output_buffer)
        output_buffer.seek(0)

        merged_bytes = output_buffer.getvalue()
        logger.info(f"Successfully merged {len(pdf_bytes_list)} documents into {len(writer.pages)} pages")

        return merged_bytes

    @classmethod
    def get_supported_extensions(cls) -> set:
        """Return the set of supported file extensions."""
        return cls.SUPPORTED_EXTENSIONS
