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

    @override_settings(DATE_FORMAT_JS="yyyy-MM-dd")
    def test_public_app_config_uses_settings_date_format(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["dateFormat"], "yyyy-MM-dd")

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
