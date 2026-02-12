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
