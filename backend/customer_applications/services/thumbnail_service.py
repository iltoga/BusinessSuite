"""
FILE_ROLE: Service-layer logic for the customer applications app.

KEY_COMPONENTS:
- ThumbnailService: Service class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on its narrow layer boundary and avoid moving cross-cutting workflow code here.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

import os
import posixpath
from dataclasses import dataclass
from io import BytesIO
from logging import getLogger
from typing import Optional

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from pdf2image import convert_from_bytes
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError
from PIL import Image, ImageOps, UnidentifiedImageError

logger = getLogger(__name__)


@dataclass(frozen=True)
class ThumbnailPayload:
    image_bytes: bytes
    extension: str = "jpg"
    mime_type: str = "image/jpeg"


class DocumentThumbnailService:
    """Generate and persist thumbnails for document image/PDF uploads."""

    def __init__(self):
        configured_size = getattr(settings, "DOCUMENT_THUMBNAIL_SIZE", (480, 480))
        if isinstance(configured_size, (list, tuple)) and len(configured_size) == 2:
            width = max(1, int(configured_size[0]))
            height = max(1, int(configured_size[1]))
            self.thumbnail_size = (width, height)
        else:
            self.thumbnail_size = (480, 480)

        self.jpeg_quality = max(50, min(95, int(getattr(settings, "DOCUMENT_THUMBNAIL_JPEG_QUALITY", 82))))
        self.pdf_dpi = max(72, int(getattr(settings, "DOCUMENT_THUMBNAIL_PDF_DPI", 160)))
        self.poppler_path = getattr(settings, "POPPLER_PATH", None)

    def sync_for_document(self, document) -> Optional[str]:
        """
        Generate and save a thumbnail for a document file.

        Returns the saved storage path or None when no thumbnail was generated.
        """
        source_path = getattr(getattr(document, "file", None), "name", "") or ""
        if not source_path:
            self.clear_for_document(document)
            return None

        try:
            with default_storage.open(source_path, "rb") as source_file:
                source_bytes = source_file.read()
        except Exception as exc:
            logger.warning("Unable to read source file for thumbnail generation '%s': %s", source_path, exc)
            self.clear_for_document(document)
            return None

        payload = self._build_thumbnail_payload(source_bytes=source_bytes, source_name=source_path)
        if payload is None:
            self.clear_for_document(document)
            return None

        target_path = self._build_storage_path(document=document, extension=payload.extension)
        previous_thumbnail_path = getattr(getattr(document, "thumbnail", None), "name", "") or ""
        if previous_thumbnail_path and previous_thumbnail_path != target_path:
            self._delete_storage_object(previous_thumbnail_path)
        self._delete_storage_object(target_path)

        saved_path = default_storage.save(target_path, ContentFile(payload.image_bytes))
        thumbnail_url = self._safe_storage_url(saved_path) or ""

        document.__class__.objects.filter(pk=document.pk).update(
            thumbnail=saved_path,
            thumbnail_link=thumbnail_url,
        )
        document.thumbnail.name = saved_path
        document.thumbnail_link = thumbnail_url
        return saved_path

    def clear_for_document(self, document) -> None:
        """Delete the current thumbnail object and clear persisted thumbnail fields."""
        current_thumbnail_path = getattr(getattr(document, "thumbnail", None), "name", "") or ""
        if current_thumbnail_path:
            self._delete_storage_object(current_thumbnail_path)

        if getattr(document, "pk", None):
            document.__class__.objects.filter(pk=document.pk).update(
                thumbnail="",
                thumbnail_link="",
            )
        document.thumbnail.name = ""
        document.thumbnail_link = ""

    def _build_thumbnail_payload(self, *, source_bytes: bytes, source_name: str) -> Optional[ThumbnailPayload]:
        if not source_bytes:
            return None

        image = None
        try:
            if self._is_pdf(source_name=source_name, source_bytes=source_bytes):
                image = self._pdf_first_page_to_image(source_bytes)
            else:
                image = self._bytes_to_image(source_bytes)
            if image is None:
                return None

            with image:
                normalized = ImageOps.exif_transpose(image)
                processed = self._prepare_rgb(normalized)
                processed.thumbnail(self.thumbnail_size, self._resample_filter())

                output = BytesIO()
                processed.save(
                    output,
                    format="JPEG",
                    quality=self.jpeg_quality,
                    optimize=True,
                    progressive=True,
                )
                return ThumbnailPayload(image_bytes=output.getvalue())
        except Exception as exc:
            logger.warning("Thumbnail generation failed for '%s': %s", source_name, exc)
            return None

    def _pdf_first_page_to_image(self, source_bytes: bytes) -> Optional[Image.Image]:
        try:
            images = convert_from_bytes(
                source_bytes,
                first_page=1,
                last_page=1,
                dpi=self.pdf_dpi,
                fmt="jpeg",
                thread_count=1,
                single_file=True,
                poppler_path=self.poppler_path,
            )
        except (PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError) as exc:
            logger.warning("pdf2image failed while generating thumbnail: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Unexpected PDF thumbnail conversion error: %s", exc)
            return None

        if not images:
            return None
        return images[0]

    def _bytes_to_image(self, source_bytes: bytes) -> Optional[Image.Image]:
        try:
            return Image.open(BytesIO(source_bytes))
        except UnidentifiedImageError:
            return None

    def _build_storage_path(self, *, document, extension: str) -> str:
        ext = extension.lower().lstrip(".") or "jpg"
        document_id = getattr(document, "pk", None) or "new"
        app_folder = ""
        doc_application = getattr(document, "doc_application", None)
        if doc_application is not None:
            app_folder = str(getattr(doc_application, "upload_folder", "") or "")
        app_folder = app_folder.strip("/ ")

        if app_folder:
            return f"{app_folder}/thumbnails/document_{document_id}.{ext}"

        file_name = getattr(getattr(document, "file", None), "name", "") or ""
        parent = posixpath.dirname(file_name).strip("/ ")
        if parent:
            return f"{parent}/thumbnails/document_{document_id}.{ext}"
        return f"thumbnails/document_{document_id}.{ext}"

    @staticmethod
    def _is_pdf(*, source_name: str, source_bytes: bytes) -> bool:
        _, extension = os.path.splitext(source_name.lower())
        return extension == ".pdf" or source_bytes.startswith(b"%PDF-")

    @staticmethod
    def _prepare_rgb(image: Image.Image) -> Image.Image:
        if image.mode == "RGB":
            return image
        if image.mode in {"RGBA", "LA"}:
            alpha = image.convert("RGBA")
            background = Image.new("RGB", alpha.size, (255, 255, 255))
            background.paste(alpha, mask=alpha.split()[-1])
            return background
        return image.convert("RGB")

    @staticmethod
    def _resample_filter():
        try:
            return Image.Resampling.LANCZOS
        except AttributeError:
            return Image.LANCZOS

    @staticmethod
    def _delete_storage_object(path: str) -> None:
        if not path:
            return
        try:
            if default_storage.exists(path):
                default_storage.delete(path)
        except Exception:
            logger.debug("Ignoring thumbnail delete error for path '%s'", path, exc_info=True)

    @staticmethod
    def _safe_storage_url(path: str) -> Optional[str]:
        try:
            return default_storage.url(path)
        except Exception:
            return None
