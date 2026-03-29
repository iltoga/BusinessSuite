"""Tests for Google client import and bootstrap helpers."""

import importlib
import sys
from unittest.mock import patch

from django.test import SimpleTestCase


class GoogleClientImportTests(SimpleTestCase):
    def test_google_client_module_import_does_not_touch_app_settings(self):
        sys.modules.pop("core.utils.google_client", None)

        with patch(
            "core.services.app_setting_service.AppSettingService.get_effective_raw",
            side_effect=AssertionError("google_client import must not query AppSettingService"),
        ) as mocked_get_effective_raw:
            importlib.import_module("core.utils.google_client")

        mocked_get_effective_raw.assert_not_called()
