import sys
import types
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings


class DropEasyAuditCommandTests(TestCase):
    def test_noop_when_not_installed(self):
        # easyaudit not in INSTALLED_APPS -> should warn and exit without calling migrate
        # Patch the inner call_command used by the command implementation so we can observe whether
        # the command attempted to call migrate without preventing the command from running itself.
        with patch("core.management.commands.drop_easyaudit.call_command") as mock_inner_call:
            out = self.run_management_command("drop_easyaudit")
            self.assertIn("easyaudit is not present", out)
            mock_inner_call.assert_not_called()

    def test_dry_run_when_installed(self):
        # Simulate easyaudit being present by temporarily adding a dummy module so Django
        # can import the app when setting INSTALLED_APPS.
        dummy = types.ModuleType("easyaudit")
        # provide a __path__ so Django accepts it as a package module during testing
        dummy.__path__ = ["."]
        with patch.dict(sys.modules, {"easyaudit": dummy}):
            # Keep core present so the management command is discoverable
            with override_settings(INSTALLED_APPS=["core", "easyaudit"]):
                with patch("core.management.commands.drop_easyaudit.call_command") as mock_inner_call:
                    out = self.run_management_command("drop_easyaudit")
                    self.assertIn("Dry-run", out)
                    mock_inner_call.assert_not_called()

    def test_apply_when_installed_and_yes(self):
        dummy = types.ModuleType("easyaudit")
        # provide a __path__ so Django accepts it as a package module during testing
        dummy.__path__ = ["."]
        with patch.dict(sys.modules, {"easyaudit": dummy}):
            # Keep core present so the management command is discoverable
            with override_settings(INSTALLED_APPS=["core", "easyaudit"]):
                with patch("core.management.commands.drop_easyaudit.call_command") as mock_inner_call:
                    out = self.run_management_command("drop_easyaudit", "--yes")
                    mock_inner_call.assert_called_once_with("migrate", "easyaudit", "zero")
                    self.assertIn("Successfully migrated easyaudit to zero", out)

    # helper to capture management command output
    def run_management_command(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command(*args, stdout=out)
        return out.getvalue()
