from core.models import AppSetting
from core.models.ui_settings import UiSettings
from django.test import Client, TestCase, override_settings
from django.urls import reverse


class PublicAppConfigTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("api-public-app-config")

    def test_public_app_config_contains_date_format(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("dateFormat", payload)
        self.assertIsInstance(payload["dateFormat"], str)
        self.assertIn("baseCurrency", payload)
        self.assertIsInstance(payload["baseCurrency"], str)

    @override_settings(DATE_FORMAT_JS="yyyy-MM-dd")
    def test_public_app_config_uses_settings_date_format(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["dateFormat"], "yyyy-MM-dd")

    @override_settings(BASE_CURRENCY="USD")
    def test_public_app_config_uses_settings_base_currency(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["baseCurrency"], "USD")

    @override_settings(MOCK_AUTH_ENABLED=False)
    def test_public_app_config_returns_mock_auth_disabled_flag(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("MOCK_AUTH_ENABLED", payload)
        self.assertIs(payload["MOCK_AUTH_ENABLED"], False)

    @override_settings(MOCK_AUTH_ENABLED=True)
    def test_public_app_config_returns_mock_auth_enabled_flag(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("MOCK_AUTH_ENABLED", payload)
        self.assertIs(payload["MOCK_AUTH_ENABLED"], True)

    def test_public_app_config_returns_overlay_menu_setting(self):
        settings_obj = UiSettings.get_solo()
        settings_obj.use_overlay_menu = True
        settings_obj.save(update_fields=["use_overlay_menu", "updated_at"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("useOverlayMenu", payload)
        self.assertIs(payload["useOverlayMenu"], True)

    def test_public_app_config_does_not_expose_fcm_fields(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        disallowed_keys = {
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
        self.assertTrue(disallowed_keys.isdisjoint(payload.keys()))

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
