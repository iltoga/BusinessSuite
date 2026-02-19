from __future__ import annotations

import os
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile, UploadedFile

from core.utils.imgutils import convert_and_resize_image


class PassportFileProcessingError(Exception):
    """Raised when passport file preprocessing fails."""


def _is_pdf(uploaded_file: UploadedFile) -> bool:
    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    file_name = (getattr(uploaded_file, "name", "") or "").lower()
    return content_type == "application/pdf" or file_name.endswith(".pdf")


def normalize_passport_file(uploaded_file: UploadedFile | None) -> UploadedFile | None:
    """Convert PDF uploads to PNG so passport previews work in image-only views."""
    if not uploaded_file or not _is_pdf(uploaded_file):
        return uploaded_file

    try:
        image, _ = convert_and_resize_image(
            uploaded_file,
            "application/pdf",
            return_encoded=False,
            resize=False,
            dpi=300,
        )
    except Exception as exc:
        raise PassportFileProcessingError(f"Failed to process passport PDF: {exc}") from exc

    png_buffer = BytesIO()
    image.save(png_buffer, format="PNG", compress_level=1, optimize=False)
    png_bytes = png_buffer.getvalue()
    if not png_bytes:
        raise PassportFileProcessingError("Failed to process passport PDF: empty PNG output")

    base_name = os.path.splitext(os.path.basename(uploaded_file.name or "passport"))[0] or "passport"
    return SimpleUploadedFile(
        name=f"{base_name}.png",
        content=png_bytes,
        content_type="image/png",
    )

