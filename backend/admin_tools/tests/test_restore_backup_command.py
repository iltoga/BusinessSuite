import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from admin_tools import services


class RestoreBackupCommandTests(SimpleTestCase):
    def test_restores_by_filename_from_backups_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_name = "backup-20260218-120000.tar.zst"
            backup_path = Path(tmpdir) / backup_name
            backup_path.write_text("dummy", encoding="utf-8")

            with patch.object(services, "BACKUPS_DIR", tmpdir), patch(
                "admin_tools.services.restore_from_file",
                return_value=iter(["Restore completed successfully."]),
            ) as mock_restore:
                out = StringIO()
                call_command("restore_backup", backup_name, "--force", "--include-users", stdout=out)

            mock_restore.assert_called_once_with(str(backup_path), include_users=True)
            output = out.getvalue()
            self.assertIn("Starting restore from:", output)
            self.assertIn("Restore completed.", output)

    def test_aborts_without_force_when_user_declines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_name = "backup-20260218-120000.tar.zst"
            backup_path = Path(tmpdir) / backup_name
            backup_path.write_text("dummy", encoding="utf-8")

            with patch.object(services, "BACKUPS_DIR", tmpdir), patch("builtins.input", return_value="n"), patch(
                "admin_tools.services.restore_from_file"
            ) as mock_restore:
                with self.assertRaises(CommandError) as raised:
                    call_command("restore_backup", backup_name)

            self.assertIn("aborted by user", str(raised.exception).lower())
            mock_restore.assert_not_called()

    def test_raises_when_backup_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(services, "BACKUPS_DIR", tmpdir):
                with self.assertRaises(CommandError) as raised:
                    call_command("restore_backup", "missing.tar.zst", "--force")

            self.assertIn("not found", str(raised.exception).lower())
