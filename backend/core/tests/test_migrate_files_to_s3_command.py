from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.models import DocumentOCRJob, OCRJob
from django.core.management import call_command
from django.test import TestCase, override_settings
from invoices.models.import_job import InvoiceImportItem, InvoiceImportJob


class MigrateFilesToS3CommandTests(TestCase):
    def _fake_storage_open(self, name, mode="rb"):
        if "w" not in mode:
            raise ValueError("Test stub only supports write mode")
        return BytesIO()

    @override_settings(USE_CLOUD_STORAGE=True)
    def test_migrates_extra_dirs_and_rewires_path_fields(self):
        with TemporaryDirectory() as tmpdir:
            source_root = Path(tmpdir)
            tmp_file = source_root / "tmpfiles" / "sample.txt"
            default_doc = source_root / "default_documents" / "default_sponsor_document.pdf"
            tmp_file.parent.mkdir(parents=True, exist_ok=True)
            default_doc.parent.mkdir(parents=True, exist_ok=True)
            tmp_file.write_bytes(b"tmp")
            default_doc.write_bytes(b"default")

            job = OCRJob.objects.create(
                status=OCRJob.STATUS_COMPLETED,
                progress=100,
                file_path=str(tmp_file.resolve()),
                file_url="http://old.local/tmpfiles/sample.txt",
                result={},
            )
            doc_job = DocumentOCRJob.objects.create(
                status=DocumentOCRJob.STATUS_COMPLETED,
                progress=100,
                file_path=str(tmp_file.resolve()),
                file_url="http://old.local/tmpfiles/sample.txt",
            )
            import_job = InvoiceImportJob.objects.create()
            import_item = InvoiceImportItem.objects.create(
                job=import_job,
                filename="sample.txt",
                file_path=str(tmp_file.resolve()),
            )

            with patch(
                "core.management.commands.migrate_files_to_s3.default_storage.exists",
                side_effect=lambda key: False,
            ) as mock_exists, patch(
                "core.management.commands.migrate_files_to_s3.default_storage.open",
                side_effect=self._fake_storage_open,
            ), patch(
                "core.management.commands.migrate_files_to_s3.default_storage.url",
                side_effect=lambda key: f"https://s3.example/{key}",
            ):
                out = StringIO()
                call_command("migrate_files_to_s3", "--source-root", str(source_root), stdout=out)

            job.refresh_from_db()
            doc_job.refresh_from_db()
            import_item.refresh_from_db()

            self.assertEqual(job.file_path, "tmpfiles/sample.txt")
            self.assertEqual(job.file_url, "https://s3.example/tmpfiles/sample.txt")
            self.assertEqual(doc_job.file_path, "tmpfiles/sample.txt")
            self.assertEqual(doc_job.file_url, "https://s3.example/tmpfiles/sample.txt")
            self.assertEqual(import_item.file_path, "tmpfiles/sample.txt")

            checked_keys = [call.args[0] for call in mock_exists.call_args_list]
            self.assertIn("tmpfiles/sample.txt", checked_keys)
            self.assertIn("default_documents/default_sponsor_document.pdf", checked_keys)

    @override_settings(USE_CLOUD_STORAGE=True)
    def test_dry_run_keeps_db_unchanged(self):
        with TemporaryDirectory() as tmpdir:
            source_root = Path(tmpdir)
            tmp_file = source_root / "tmpfiles" / "sample.txt"
            tmp_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file.write_bytes(b"tmp")

            job = OCRJob.objects.create(
                status=OCRJob.STATUS_COMPLETED,
                progress=100,
                file_path=str(tmp_file.resolve()),
                file_url="http://old.local/tmpfiles/sample.txt",
                result={},
            )

            with patch(
                "core.management.commands.migrate_files_to_s3.default_storage.exists",
                side_effect=lambda key: False,
            ), patch(
                "core.management.commands.migrate_files_to_s3.default_storage.open",
                side_effect=self._fake_storage_open,
            ), patch(
                "core.management.commands.migrate_files_to_s3.default_storage.url",
                side_effect=lambda key: f"https://s3.example/{key}",
            ):
                out = StringIO()
                call_command("migrate_files_to_s3", "--dry-run", "--source-root", str(source_root), stdout=out)

            job.refresh_from_db()
            self.assertEqual(job.file_path, str(tmp_file.resolve()))
            self.assertEqual(job.file_url, "http://old.local/tmpfiles/sample.txt")
