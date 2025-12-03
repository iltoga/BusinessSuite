"""
PDF Converter Utility
====================

Cross-platform document conversion to PDF using LibreOffice.
Supports DOCX files and common image formats (JPG, PNG, TIFF, BMP, GIF).

System Requirements
-------------------
The following system packages must be installed:

**macOS (via Homebrew):**
    brew install --cask libreoffice

**Debian/Ubuntu (via apt):**
    apt-get install libreoffice-writer-nogui

Usage Example
-------------
    from core.utils.pdf_converter import PDFConverter

    # Convert DOCX to PDF (returns bytes)
    pdf_bytes = PDFConverter.docx_to_pdf('/path/to/document.docx')

    # Convert image to PDF
    pdf_bytes = PDFConverter.image_to_pdf('/path/to/image.jpg')

    # Convert from BytesIO
    pdf_bytes = PDFConverter.docx_buffer_to_pdf(docx_buffer)

Note:
    For DOCX conversion, this module uses LibreOffice in headless mode
    which provides the best fidelity for complex Word documents with
    tables, images, and precise formatting.

    For images, Pillow is used to directly save the image as a PDF.
"""

import logging
import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


class PDFConverterError(Exception):
    """Custom exception for PDF conversion errors."""

    pass


class PDFConverter:
    """
    Utility class for converting documents to PDF.

    Supports:
    - DOCX files (via LibreOffice)
    - Images: JPEG, PNG, TIFF, BMP, GIF (via Pillow)
    """

    # Supported image extensions
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".gif", ".webp"}

    # Supported document extensions
    DOCX_EXTENSIONS = {".docx", ".doc"}

    # LibreOffice conversion timeout in seconds
    CONVERSION_TIMEOUT = 60

    @classmethod
    def is_libreoffice_available(cls) -> bool:
        """Check if LibreOffice (soffice) binary is available on the system."""
        return shutil.which("soffice") is not None

    @classmethod
    def _get_soffice_path(cls) -> str:
        """Get the path to the soffice binary."""
        soffice = shutil.which("soffice")
        if not soffice:
            raise PDFConverterError(
                "LibreOffice is not installed. Please install it:\n"
                "  macOS: brew install --cask libreoffice\n"
                "  Debian/Ubuntu: apt-get install libreoffice-writer-nogui"
            )
        return soffice

    @classmethod
    def docx_to_pdf(
        cls,
        docx_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
    ) -> bytes:
        """
        Convert a DOCX file to PDF using LibreOffice.

        Args:
            docx_path: Path to the input DOCX file.
            output_path: Optional path for the output PDF. If None, returns bytes.

        Returns:
            PDF content as bytes.

        Raises:
            PDFConverterError: If conversion fails.
            FileNotFoundError: If the input file doesn't exist.
        """
        docx_path = Path(docx_path)

        if not docx_path.exists():
            raise FileNotFoundError(f"DOCX file not found: {docx_path}")

        soffice = cls._get_soffice_path()

        temp_dir = None
        try:
            # Create temporary directory for conversion output
            temp_dir = tempfile.mkdtemp(prefix="docx_to_pdf_")

            # Build LibreOffice command
            # --headless: run without GUI
            # --invisible: no splash screen
            # --nodefault: don't start with an empty document
            # --nofirststartwizard: skip first-run wizard
            # --nolockcheck: don't check for lock files (safe in containers)
            # --nologo: no logo on startup
            # --norestore: don't restore previous session
            # --convert-to pdf: output format
            # --outdir: output directory
            cmd = [
                soffice,
                "--headless",
                "--invisible",
                "--nodefault",
                "--nofirststartwizard",
                "--nolockcheck",
                "--nologo",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                str(temp_dir),
                str(docx_path),
            ]

            logger.debug(f"Running LibreOffice conversion: {' '.join(cmd)}")

            try:
                result = subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=cls.CONVERSION_TIMEOUT,
                )
                logger.debug(f"LibreOffice stdout: {result.stdout}")
                if result.stderr:
                    logger.debug(f"LibreOffice stderr: {result.stderr}")
            except subprocess.TimeoutExpired:
                raise PDFConverterError(f"PDF conversion timed out after {cls.CONVERSION_TIMEOUT} seconds.")
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr if e.stderr else str(e)
                raise PDFConverterError(f"LibreOffice conversion failed: {error_msg}")

            # Find the output PDF file
            pdf_filename = docx_path.stem + ".pdf"
            temp_pdf_path = Path(temp_dir) / pdf_filename

            if not temp_pdf_path.exists():
                raise PDFConverterError(
                    "PDF conversion failed: output file not found. " "LibreOffice may have encountered an error."
                )

            # Read the PDF content
            pdf_bytes = temp_pdf_path.read_bytes()
            logger.info(f"PDF generated successfully, size: {len(pdf_bytes)} bytes")

            # Write to output file if specified
            if output_path:
                output_path = Path(output_path)
                output_path.write_bytes(pdf_bytes)
                logger.info(f"PDF saved to: {output_path}")

            return pdf_bytes

        except PDFConverterError:
            raise
        except Exception as e:
            logger.error(f"Failed to convert DOCX to PDF: {e}")
            raise PDFConverterError(f"DOCX to PDF conversion failed: {e}") from e

        finally:
            # Cleanup temporary directory
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    @classmethod
    def docx_buffer_to_pdf(
        cls,
        docx_buffer: BytesIO,
        output_path: Optional[Union[str, Path]] = None,
    ) -> bytes:
        """
        Convert a DOCX buffer (BytesIO) to PDF.

        Args:
            docx_buffer: BytesIO containing the DOCX content.
            output_path: Optional path for the output PDF.

        Returns:
            PDF content as bytes.

        Raises:
            PDFConverterError: If conversion fails.
        """
        temp_dir = None
        try:
            # Create temporary directory and save the DOCX buffer
            temp_dir = tempfile.mkdtemp(prefix="docx_buffer_to_pdf_")
            temp_docx_path = Path(temp_dir) / "document.docx"

            # Write buffer to temp file
            docx_buffer.seek(0)
            temp_docx_path.write_bytes(docx_buffer.read())

            # Use the file-based conversion
            return cls.docx_to_pdf(temp_docx_path, output_path)

        finally:
            # Cleanup temporary directory
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    @classmethod
    def image_to_pdf(
        cls,
        image_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
    ) -> bytes:
        """
        Convert an image file to PDF using Pillow.

        Args:
            image_path: Path to the input image file.
            output_path: Optional path for the output PDF.

        Returns:
            PDF content as bytes.

        Raises:
            PDFConverterError: If conversion fails.
            FileNotFoundError: If the input file doesn't exist.
        """
        from PIL import Image

        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        ext = image_path.suffix.lower()
        if ext not in cls.IMAGE_EXTENSIONS:
            raise PDFConverterError(
                f"Unsupported image format: {ext}. " f"Supported formats: {', '.join(cls.IMAGE_EXTENSIONS)}"
            )

        try:
            # Open the image
            with Image.open(image_path) as img:
                pdf_bytes = cls._image_obj_to_pdf(img)

            # Write to output file if specified
            if output_path:
                output_path = Path(output_path)
                output_path.write_bytes(pdf_bytes)
                logger.info(f"PDF saved to: {output_path}")

            return pdf_bytes

        except PDFConverterError:
            raise
        except Exception as e:
            logger.error(f"Failed to convert image to PDF: {e}")
            raise PDFConverterError(f"Image to PDF conversion failed: {e}") from e

    @classmethod
    def image_buffer_to_pdf(
        cls,
        image_buffer: BytesIO,
        output_path: Optional[Union[str, Path]] = None,
    ) -> bytes:
        """
        Convert an image buffer (BytesIO) to PDF.

        Args:
            image_buffer: BytesIO containing the image data.
            output_path: Optional path for the output PDF.

        Returns:
            PDF content as bytes.

        Raises:
            PDFConverterError: If conversion fails.
        """
        from PIL import Image

        try:
            image_buffer.seek(0)
            with Image.open(image_buffer) as img:
                pdf_bytes = cls._image_obj_to_pdf(img)

            # Write to output file if specified
            if output_path:
                output_path = Path(output_path)
                output_path.write_bytes(pdf_bytes)
                logger.info(f"PDF saved to: {output_path}")

            return pdf_bytes

        except PDFConverterError:
            raise
        except Exception as e:
            logger.error(f"Failed to convert image buffer to PDF: {e}")
            raise PDFConverterError(f"Image buffer to PDF conversion failed: {e}") from e

    @classmethod
    def _image_obj_to_pdf(cls, img) -> bytes:
        """
        Convert a PIL Image object to PDF bytes.

        Args:
            img: PIL Image object.

        Returns:
            PDF content as bytes.
        """
        from PIL import Image

        # Convert to RGB if necessary (e.g., RGBA or palette images)
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            # Create white background for transparent images
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Save as PDF to BytesIO
        pdf_buffer = BytesIO()
        img.save(pdf_buffer, format="PDF", resolution=100.0)
        pdf_buffer.seek(0)

        logger.info(f"Image converted to PDF, size: {len(pdf_buffer.getvalue())} bytes")
        return pdf_buffer.getvalue()

    @classmethod
    def convert_to_pdf(
        cls,
        input_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
    ) -> bytes:
        """
        Auto-detect file type and convert to PDF.

        Supports DOCX files and common image formats.

        Args:
            input_path: Path to the input file.
            output_path: Optional path for the output PDF.

        Returns:
            PDF content as bytes.

        Raises:
            PDFConverterError: If conversion fails or format is unsupported.
        """
        input_path = Path(input_path)
        ext = input_path.suffix.lower()

        if ext in cls.DOCX_EXTENSIONS:
            return cls.docx_to_pdf(input_path, output_path)
        elif ext in cls.IMAGE_EXTENSIONS:
            return cls.image_to_pdf(input_path, output_path)
        else:
            raise PDFConverterError(
                f"Unsupported file format: {ext}. " f"Supported formats: DOCX, DOC, {', '.join(cls.IMAGE_EXTENSIONS)}"
            )

    @classmethod
    def convert_buffer_to_pdf(
        cls,
        buffer: BytesIO,
        file_type: str,
        output_path: Optional[Union[str, Path]] = None,
    ) -> bytes:
        """
        Convert a buffer to PDF based on file type.

        Args:
            buffer: BytesIO containing the file content.
            file_type: File type/extension (e.g., 'docx', 'jpg', 'png').
            output_path: Optional path for the output PDF.

        Returns:
            PDF content as bytes.

        Raises:
            PDFConverterError: If conversion fails or format is unsupported.
        """
        # Normalize file type
        file_type = file_type.lower().strip(".")

        if file_type in {"docx", "doc"}:
            return cls.docx_buffer_to_pdf(buffer, output_path)
        elif f".{file_type}" in cls.IMAGE_EXTENSIONS:
            return cls.image_buffer_to_pdf(buffer, output_path)
        else:
            raise PDFConverterError(
                f"Unsupported file type: {file_type}. "
                f"Supported types: docx, doc, {', '.join(ext.strip('.') for ext in cls.IMAGE_EXTENSIONS)}"
            )
