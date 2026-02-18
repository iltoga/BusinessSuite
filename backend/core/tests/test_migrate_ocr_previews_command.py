from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from core.models import OCRJob


class MigrateOcrPreviewsCommandTests(TestCase):
    def test_migrates_b64_preview_to_storage_path(self):
        job = OCRJob.objects.create(
            status=OCRJob.STATUS_COMPLETED,
            progress=100,
            file_path="tmpfiles/in.png",
            file_url="https://example.com/in.png",
            result={"b64_resized_image": "aGVsbG8=", "mrz_data": {"number": "ABC123"}},
        )

        with patch(
            "core.management.commands.migrate_ocr_previews_to_storage.upload_ocr_preview_from_base64",
            return_value=f"ocr_previews/{job.id}.png",
        ) as mock_upload:
            stdout = StringIO()
            call_command("migrate_ocr_previews_to_storage", stdout=stdout)

        job.refresh_from_db()
        self.assertEqual(job.result.get("preview_storage_path"), f"ocr_previews/{job.id}.png")
        self.assertEqual(job.result.get("preview_mime_type"), "image/png")
        self.assertNotIn("b64_resized_image", job.result)
        self.assertEqual(job.result.get("mrz_data"), {"number": "ABC123"})
        mock_upload.assert_called_once()

    def test_dry_run_does_not_modify_rows(self):
        job = OCRJob.objects.create(
            status=OCRJob.STATUS_COMPLETED,
            progress=100,
            file_path="tmpfiles/in.png",
            file_url="https://example.com/in.png",
            result={"b64_resized_image": "aGVsbG8=", "mrz_data": {"number": "ABC123"}},
        )

        with patch("core.management.commands.migrate_ocr_previews_to_storage.upload_ocr_preview_from_base64") as mock_upload:
            stdout = StringIO()
            call_command("migrate_ocr_previews_to_storage", "--dry-run", stdout=stdout)

        job.refresh_from_db()
        self.assertIn("b64_resized_image", job.result)
        self.assertNotIn("preview_storage_path", job.result)
        mock_upload.assert_not_called()
