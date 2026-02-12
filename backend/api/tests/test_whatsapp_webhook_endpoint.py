import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse


class WhatsappWebhookEndpointTests(TestCase):
    def test_verification_challenge_success(self):
        url = reverse("api-whatsapp-webhook")
        with override_settings(META_TOKEN_CLIENT="verify-token-123"):
            response = self.client.get(
                url,
                {
                    "hub.mode": "subscribe",
                    "hub.verify_token": "verify-token-123",
                    "hub.challenge": "challenge-value",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode("utf-8"), "challenge-value")

    def test_verification_challenge_rejects_invalid_token(self):
        url = reverse("api-whatsapp-webhook")
        with override_settings(META_TOKEN_CLIENT="verify-token-123"):
            response = self.client.get(
                url,
                {
                    "hub.mode": "subscribe",
                    "hub.verify_token": "wrong-token",
                    "hub.challenge": "challenge-value",
                },
            )

        self.assertEqual(response.status_code, 403)

    def test_post_rejects_invalid_signature(self):
        url = reverse("api-whatsapp-webhook")
        payload = {"object": "whatsapp_business_account", "entry": []}

        with override_settings(META_APP_SECRET="test-secret", META_WEBHOOK_ENFORCE_SIGNATURE=True):
            response = self.client.post(
                url,
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256="sha256=invalid",
            )

        self.assertEqual(response.status_code, 403)

    @patch("notifications.services.providers.process_whatsapp_webhook_payload")
    def test_post_accepts_valid_signature(self, process_mock):
        url = reverse("api-whatsapp-webhook")
        payload = {"object": "whatsapp_business_account", "entry": []}
        raw_body = json.dumps(payload).encode("utf-8")
        signature = "sha256=" + hmac.new(b"test-secret", raw_body, hashlib.sha256).hexdigest()

        with override_settings(META_APP_SECRET="test-secret", META_WEBHOOK_ENFORCE_SIGNATURE=True):
            response = self.client.post(
                url,
                data=raw_body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=signature,
            )

        self.assertEqual(response.status_code, 200)
        process_mock.assert_called_once()

    @patch("notifications.services.providers.process_whatsapp_webhook_payload")
    def test_post_allows_invalid_signature_when_enforcement_disabled(self, process_mock):
        url = reverse("api-whatsapp-webhook")
        payload = {"object": "whatsapp_business_account", "entry": []}

        with override_settings(META_APP_SECRET="test-secret", META_WEBHOOK_ENFORCE_SIGNATURE=False):
            response = self.client.post(
                url,
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256="sha256=invalid",
            )

        self.assertEqual(response.status_code, 200)
        process_mock.assert_called_once()
