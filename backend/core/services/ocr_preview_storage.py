import base64
import binascii

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def _normalize_base64_payload(payload: str) -> str:
    value = payload.strip()
    if value.startswith("data:") and "," in value:
        value = value.split(",", 1)[1]

    missing_padding = len(value) % 4
    if missing_padding:
        value += "=" * (4 - missing_padding)

    return value


def decode_base64_image(payload: str) -> bytes:
    if not payload:
        raise ValueError("Empty base64 payload")

    normalized_payload = _normalize_base64_payload(payload)
    try:
        image_bytes = base64.b64decode(normalized_payload, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid base64 image payload") from exc

    if not image_bytes:
        raise ValueError("Decoded base64 payload is empty")
    return image_bytes


def get_ocr_preview_storage_prefix() -> str:
    prefix = str(getattr(settings, "OCR_PREVIEW_STORAGE_PREFIX", "ocr_previews") or "ocr_previews")
    return prefix.strip("/ ")


def build_ocr_preview_storage_path(job_id: str, extension: str = "png") -> str:
    ext = extension.lower().lstrip(".") or "png"
    return f"{get_ocr_preview_storage_prefix()}/{job_id}.{ext}"


def upload_ocr_preview_bytes(job_id: str, image_bytes: bytes, extension: str = "png", overwrite: bool = True) -> str:
    target_path = build_ocr_preview_storage_path(str(job_id), extension=extension)

    if overwrite:
        try:
            if default_storage.exists(target_path):
                default_storage.delete(target_path)
        except Exception:
            pass

    return default_storage.save(target_path, ContentFile(image_bytes))


def upload_ocr_preview_from_base64(
    job_id: str, payload: str, extension: str = "png", overwrite: bool = True
) -> str:
    return upload_ocr_preview_bytes(
        job_id=str(job_id),
        image_bytes=decode_base64_image(payload),
        extension=extension,
        overwrite=overwrite,
    )


def get_ocr_preview_url(storage_path: str | None) -> str | None:
    if not storage_path:
        return None
    return default_storage.url(storage_path)
