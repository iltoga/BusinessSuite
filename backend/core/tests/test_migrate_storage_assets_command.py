from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase


class MigrateStorageAssetsCommandTests(SimpleTestCase):
    @patch("core.management.commands.migrate_storage_assets.call_command")
    def test_runs_both_commands_with_forwarded_options(self, mock_call_command):
        stdout = StringIO()
        call_command(
            "migrate_storage_assets",
            "--dry-run",
            "--source-root",
            "/tmp/media",
            "--extra-dir",
            "tmpfiles",
            "--batch-size",
            "123",
            "--keep-b64",
            stdout=stdout,
        )

        self.assertEqual(mock_call_command.call_count, 2)

        first_call = mock_call_command.call_args_list[0]
        self.assertEqual(first_call.args[0], "migrate_files_to_s3")
        self.assertTrue(first_call.kwargs.get("dry_run"))
        self.assertEqual(first_call.kwargs.get("source_root"), "/tmp/media")
        self.assertEqual(first_call.kwargs.get("extra_dirs"), ["tmpfiles"])

        second_call = mock_call_command.call_args_list[1]
        self.assertEqual(second_call.args[0], "migrate_ocr_previews_to_storage")
        self.assertTrue(second_call.kwargs.get("dry_run"))
        self.assertEqual(second_call.kwargs.get("batch_size"), 123)
        self.assertTrue(second_call.kwargs.get("keep_b64"))

    @patch("core.management.commands.migrate_storage_assets.call_command")
    def test_skip_flags(self, mock_call_command):
        stdout = StringIO()
        call_command("migrate_storage_assets", "--skip-files", stdout=stdout)
        self.assertEqual(mock_call_command.call_count, 1)
        self.assertEqual(mock_call_command.call_args_list[0].args[0], "migrate_ocr_previews_to_storage")

        mock_call_command.reset_mock()
        call_command("migrate_storage_assets", "--skip-ocr-previews", stdout=stdout)
        self.assertEqual(mock_call_command.call_count, 1)
        self.assertEqual(mock_call_command.call_args_list[0].args[0], "migrate_files_to_s3")
