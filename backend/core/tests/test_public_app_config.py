"""Tests for the public app configuration endpoint."""

import os
from unittest.mock import patch

from core.models import AppSetting
from core.models.ui_settings import UiSettings
from django.test import Client, TestCase, override_settings
from django.urls import reverse


class PublicAppConfigTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("api-public-app-config")

    def _clear_ui_scale_env(self):
        return patch.dict(
            os.environ,
            {
                "UI_SCALE_PERCENT": "",
                "UI_AUTO_SCALE_ENABLED": "",
                "UI_AUTO_SCALE_REFERENCE_WIDTH": "",
                "UI_AUTO_SCALE_MIN_PERCENT": "",
                "UI_AUTO_SCALE_MAX_PERCENT": "",
                "UI_AUTO_SCALE_DESKTOP_ONLY": "",
            },
            clear=False,
        )

    def test_public_app_config_contains_date_format(self):
        with self._clear_ui_scale_env():
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("dateFormat", payload)
        self.assertIsInstance(payload["dateFormat"], str)
        self.assertIn("baseCurrency", payload)
        self.assertIsInstance(payload["baseCurrency"], str)
        self.assertIn("uiScalePercent", payload)
        self.assertEqual(payload["uiScalePercent"], 100)

    def test_public_app_config_clamps_ui_scale_percent(self):
        with self._clear_ui_scale_env():
            AppSetting.objects.update_or_create(
                name="UI_SCALE_PERCENT",
                defaults={"value": "200", "scope": AppSetting.SCOPE_FRONTEND},
            )

            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["uiScalePercent"], 125)

    def test_public_app_config_contains_ui_auto_scale_defaults(self):
        with self._clear_ui_scale_env():
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["uiAutoScaleEnabled"], False)
        self.assertEqual(payload["uiAutoScaleReferenceWidth"], 1440)
        self.assertEqual(payload["uiAutoScaleMinPercent"], 95)
        self.assertEqual(payload["uiAutoScaleMaxPercent"], 105)
        self.assertEqual(payload["uiAutoScaleDesktopOnly"], True)

    def test_public_app_config_clamps_ui_auto_scale_values(self):
        with self._clear_ui_scale_env():
            AppSetting.objects.update_or_create(
                name="UI_AUTO_SCALE_REFERENCE_WIDTH",
                defaults={"value": "500", "scope": AppSetting.SCOPE_FRONTEND},
            )
            AppSetting.objects.update_or_create(
                name="UI_AUTO_SCALE_MIN_PERCENT",
                defaults={"value": "20", "scope": AppSetting.SCOPE_FRONTEND},
            )
            AppSetting.objects.update_or_create(
                name="UI_AUTO_SCALE_MAX_PERCENT",
                defaults={"value": "300", "scope": AppSetting.SCOPE_FRONTEND},
            )
            AppSetting.objects.update_or_create(
                name="UI_AUTO_SCALE_ENABLED",
                defaults={"value": "true", "scope": AppSetting.SCOPE_FRONTEND},
            )

            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["uiAutoScaleEnabled"], True)
        self.assertEqual(payload["uiAutoScaleReferenceWidth"], 1024)
        self.assertEqual(payload["uiAutoScaleMinPercent"], 25)
        self.assertEqual(payload["uiAutoScaleMaxPercent"], 125)

    def test_public_app_config_reads_ui_scale_values_from_env(self):
        with patch.dict(
            "os.environ",
            {
                "UI_SCALE_PERCENT": "90",
                "UI_AUTO_SCALE_ENABLED": "True",
                "UI_AUTO_SCALE_REFERENCE_WIDTH": "1920",
                "UI_AUTO_SCALE_MIN_PERCENT": "60",
                "UI_AUTO_SCALE_MAX_PERCENT": "150",
                "UI_AUTO_SCALE_DESKTOP_ONLY": "True",
            },
            clear=False,
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["uiScalePercent"], 90)
        self.assertEqual(payload["uiAutoScaleEnabled"], True)
        self.assertEqual(payload["uiAutoScaleReferenceWidth"], 1920)
        self.assertEqual(payload["uiAutoScaleMinPercent"], 60)
        self.assertEqual(payload["uiAutoScaleMaxPercent"], 125)
        self.assertEqual(payload["uiAutoScaleDesktopOnly"], True)

    @override_settings(MOCK_AUTH_ENABLED=False)
    def test_public_app_config_returns_mock_auth_disabled_flag(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("MOCK_AUTH_ENABLED", payload)
        self.assertIs(payload["MOCK_AUTH_ENABLED"], False)

    def test_public_app_config_returns_overlay_menu_setting(self):
        settings_obj = UiSettings.get_solo()
        settings_obj.use_overlay_menu = True
        settings_obj.save(update_fields=["use_overlay_menu", "updated_at"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("useOverlayMenu", payload)
        self.assertIs(payload["useOverlayMenu"], True)

    def test_public_app_config_exposes_fcm_fields(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        required_keys = {
            "fcmSenderId",
            "fcmVapidPublicKey",
            "fcmProjectId",
            "fcmProjectNumber",
            "fcmWebApiKey",
            "fcmWebAppId",
            "fcmWebAuthDomain",
            "fcmWebStorageBucket",
            "fcmWebMeasurementId",
        }
        for key in required_keys:
            self.assertIn(key, payload)

    def test_public_app_config_includes_frontend_and_both_scoped_db_settings(self):
        AppSetting.objects.update_or_create(
            name="PUBLIC_FEATURE_FLAG",
            defaults={"value": "true", "scope": AppSetting.SCOPE_FRONTEND},
        )
        AppSetting.objects.update_or_create(
            name="PUBLIC_MAX_UPLOAD_MB",
            defaults={"value": "25", "scope": AppSetting.SCOPE_BOTH},
        )
        AppSetting.objects.update_or_create(
            name="INTERNAL_ONLY_SECRET",
            defaults={"value": "do-not-expose", "scope": AppSetting.SCOPE_BACKEND},
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("PUBLIC_FEATURE_FLAG"), True)
        self.assertEqual(payload.get("PUBLIC_MAX_UPLOAD_MB"), 25)
        self.assertNotIn("INTERNAL_ONLY_SECRET", payload)
