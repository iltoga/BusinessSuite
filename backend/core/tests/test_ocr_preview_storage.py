from django.test import SimpleTestCase, override_settings

from core.services.ocr_preview_storage import build_ocr_preview_storage_path, decode_base64_image


class OcrPreviewStorageHelpersTests(SimpleTestCase):
    def test_decode_base64_image_supports_data_uri(self):
        payload = "data:image/png;base64,aGVsbG8="
        self.assertEqual(decode_base64_image(payload), b"hello")

    @override_settings(OCR_PREVIEW_STORAGE_PREFIX="ocr/previews")
    def test_build_storage_path_uses_configured_prefix(self):
        self.assertEqual(
            build_ocr_preview_storage_path("job-123", extension="png"),
            "ocr/previews/job-123.png",
        )
