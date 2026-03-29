"""Tests for the app setting service and runtime override behavior."""

import os
from unittest.mock import patch

from core.models import AppSetting
from core.services.app_setting_service import AppSettingScope, AppSettingService
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

LOC_MEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "app-setting-service-tests",
    },
    "select2": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "app-setting-service-tests-select2",
    },
}


@override_settings(TESTING=False, CACHES=LOC_MEM_CACHES)
class AppSettingServiceCacheTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="app-setting-user", password="testpass")
        AppSetting.objects.all().delete()
        AppSettingService.invalidate_cache()

    def tearDown(self):
        AppSetting.objects.all().delete()
        AppSettingService.invalidate_cache()

    def test_parse_helpers_normalize_common_inputs(self):
        self.assertTrue(AppSettingService.parse_bool(True))
        self.assertTrue(AppSettingService.parse_bool("yes"))
        self.assertFalse(AppSettingService.parse_bool("no"))
        self.assertTrue(AppSettingService.parse_bool("maybe", default=True))

        self.assertEqual(AppSettingService.parse_int("42"), 42)
        self.assertEqual(AppSettingService.parse_int("not-an-int", default=7), 7)

        self.assertEqual(AppSettingService.parse_float("3.5"), 3.5)
        self.assertEqual(AppSettingService.parse_float("bad", default=1.25), 1.25)

        self.assertEqual(AppSettingService.parse_list("a, b, , c"), ["a", "b", "c"])
        self.assertEqual(AppSettingService.parse_list([" a ", "", "b"]), ["a", "b"])

        self.assertEqual(AppSettingService.parse_json_like("true"), True)
        self.assertEqual(AppSettingService.parse_json_like("12"), 12)
        self.assertEqual(AppSettingService.parse_json_like("3.25"), 3.25)
        self.assertEqual(AppSettingService.parse_json_like('{"alpha": 1}'), {"alpha": 1})
        self.assertEqual(AppSettingService.parse_json_like("[1, 2]"), [1, 2])

    def test_effective_raw_prefers_runtime_override_over_env_and_settings(self):
        setting_name = "TEST_RUNTIME_SETTING"

        self.assertEqual(AppSettingService.get_effective_raw(setting_name, "hardcoded"), "hardcoded")

        with override_settings(TEST_RUNTIME_SETTING="settings-value"):
            self.assertEqual(AppSettingService.get_effective_raw(setting_name, "hardcoded"), "settings-value")

            with patch.dict(os.environ, {setting_name: "env-value"}, clear=False):
                self.assertEqual(AppSettingService.get_effective_raw(setting_name, "hardcoded"), "env-value")

                AppSettingService.set_raw(
                    name=setting_name,
                    value="db-value",
                    scope=AppSettingScope.FRONTEND,
                    description="Runtime override for tests",
                    updated_by=self.user,
                    force_override=True,
                )

                self.assertEqual(AppSettingService.get_effective_raw(setting_name, "hardcoded"), "db-value")
                metadata = AppSettingService.get_metadata(setting_name, hardcoded_default="hardcoded")
                self.assertEqual(metadata["effectiveValue"], "db-value")
                self.assertEqual(metadata["source"], "database")
                self.assertTrue(metadata["isOverridden"])
                self.assertEqual(metadata["updatedById"], self.user.id)
                self.assertEqual(metadata["scope"], AppSettingScope.FRONTEND)

    def test_scoped_values_and_delete_raw_round_trip(self):
        AppSettingService.set_raw(
            name="FRONTEND_ONLY",
            value="frontend-value",
            scope=AppSettingScope.FRONTEND,
            force_override=True,
        )
        AppSettingService.set_raw(
            name="BOTH_SCOPE",
            value="both-value",
            scope=AppSettingScope.BOTH,
            force_override=True,
        )
        AppSettingService.set_raw(
            name="BACKEND_ONLY",
            value="backend-value",
            scope=AppSettingScope.BACKEND,
            force_override=True,
        )

        scoped = AppSettingService.get_scoped_values(scopes={AppSettingScope.FRONTEND, AppSettingScope.BOTH})
        self.assertEqual(
            scoped,
            {
                "FRONTEND_ONLY": "frontend-value",
                "BOTH_SCOPE": "both-value",
            },
        )

        self.assertEqual(
            AppSettingService.get_raw("FRONTEND_ONLY", default=None, require_override=True), "frontend-value"
        )
        AppSettingService.delete_raw("FRONTEND_ONLY")
        self.assertFalse(AppSetting.objects.filter(name="FRONTEND_ONLY").exists())
        self.assertIsNone(AppSettingService.get_raw("FRONTEND_ONLY", default=None, require_override=True))
