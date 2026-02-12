from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from notifications.services.providers import WhatsappNotificationProvider, verify_meta_webhook_signature


class WhatsappMetaProviderTests(SimpleTestCase):
    @override_settings(
        META_WHATSAPP_ACCESS_TOKEN="meta-token",
        META_PHONE_NUMBER_ID="942804508924296",
        META_GRAPH_API_VERSION="v23.0",
    )
    @patch("notifications.services.providers.requests.post")
    def test_send_uses_meta_graph_messages_endpoint(self, post_mock):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "messages": [{"id": "wamid.HBgLMjQ0NTU2Njc3ODg5FQIAERgSNzY3QjM1MTQ4M0I2RDA3AA=="}]
        }
        post_mock.return_value = response

        provider = WhatsappNotificationProvider()
        message_id = provider.send(
            recipient="+6282237392596",
            subject="ignored",
            body="Hello from test",
        )

        self.assertTrue(message_id.startswith("wamid."))
        post_mock.assert_called_once()
        _, kwargs = post_mock.call_args
        self.assertEqual(
            kwargs["json"],
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": "6282237392596",
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "Hello from test",
                },
            },
        )

    @override_settings(META_WHATSAPP_ACCESS_TOKEN="", META_PHONE_NUMBER_ID="")
    def test_send_returns_queued_placeholder_when_meta_not_configured(self):
        provider = WhatsappNotificationProvider()
        result = provider.send(recipient="+6282237392596", subject="x", body="y")
        self.assertEqual(result, "queued_whatsapp:+6282237392596")

    @override_settings(
        META_WHATSAPP_ACCESS_TOKEN="meta-token",
        META_PHONE_NUMBER_ID="942804508924296",
        META_GRAPH_API_VERSION="v23.0",
        META_WHATSAPP_DEFAULT_TEMPLATE_NAME="hello_world",
        META_WHATSAPP_DEFAULT_TEMPLATE_LANG="en_US",
    )
    @patch("notifications.services.providers.requests.post")
    def test_send_falls_back_to_template_when_text_window_blocked(self, post_mock):
        blocked = Mock()
        blocked.status_code = 400
        blocked.text = '{"error":{"code":131047}}'
        blocked.json.return_value = {"error": {"code": 131047}}

        template_ok = Mock()
        template_ok.status_code = 200
        template_ok.json.return_value = {"messages": [{"id": "wamid.template.fallback"}]}

        post_mock.side_effect = [blocked, template_ok]

        provider = WhatsappNotificationProvider()
        message_id = provider.send(recipient="+6282237392596", subject="ignored", body="Hello from test")
        self.assertEqual(message_id, "wamid.template.fallback")

        self.assertEqual(post_mock.call_count, 2)
        _, first_kwargs = post_mock.call_args_list[0]
        _, second_kwargs = post_mock.call_args_list[1]
        self.assertEqual(first_kwargs["json"]["type"], "text")
        self.assertEqual(second_kwargs["json"]["type"], "template")


class MetaWebhookSignatureTests(SimpleTestCase):
    @override_settings(META_APP_SECRET="test-secret")
    def test_verify_meta_webhook_signature(self):
        raw_body = b'{"object":"whatsapp_business_account"}'
        import hashlib
        import hmac

        signature = "sha256=" + hmac.new(b"test-secret", raw_body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_meta_webhook_signature(raw_body, signature))
        self.assertFalse(verify_meta_webhook_signature(raw_body, "sha256=invalid"))
