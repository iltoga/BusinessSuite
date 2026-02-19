from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from notifications.services.meta_access_token import reset_meta_whatsapp_access_token_cache
from notifications.services.providers import WhatsappNotificationProvider, verify_meta_webhook_signature


class WhatsappMetaProviderTests(SimpleTestCase):
    def setUp(self):
        reset_meta_whatsapp_access_token_cache()

    def tearDown(self):
        reset_meta_whatsapp_access_token_cache()

    @override_settings(
        META_WHATSAPP_ACCESS_TOKEN="meta-token",
        META_PHONE_NUMBER_ID="942804508924296",
        META_GRAPH_API_VERSION="v23.0",
        META_WHATSAPP_PREFER_TEMPLATE=False,
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
        META_WHATSAPP_PREFER_TEMPLATE=False,
        META_WHATSAPP_ALLOW_TEMPLATE_FALLBACK=True,
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

    @override_settings(
        META_WHATSAPP_ACCESS_TOKEN="meta-token",
        META_PHONE_NUMBER_ID="942804508924296",
        META_GRAPH_API_VERSION="v23.0",
        META_WHATSAPP_DEFAULT_TEMPLATE_NAME="hello_world",
        META_WHATSAPP_DEFAULT_TEMPLATE_LANG="en_US",
        META_WHATSAPP_PREFER_TEMPLATE=False,
        META_WHATSAPP_ALLOW_TEMPLATE_FALLBACK=False,
    )
    @patch("notifications.services.providers.requests.post")
    def test_send_does_not_fallback_to_template_when_disabled(self, post_mock):
        blocked = Mock()
        blocked.status_code = 400
        blocked.text = '{"error":{"code":131047}}'
        blocked.json.return_value = {"error": {"code": 131047}}
        post_mock.return_value = blocked

        provider = WhatsappNotificationProvider()
        with self.assertRaises(RuntimeError):
            provider.send(recipient="+6282237392596", subject="ignored", body="Hello from test")

        post_mock.assert_called_once()
        _, kwargs = post_mock.call_args
        self.assertEqual(kwargs["json"]["type"], "text")

    @override_settings(
        META_WHATSAPP_ACCESS_TOKEN="meta-token",
        META_PHONE_NUMBER_ID="942804508924296",
        META_GRAPH_API_VERSION="v23.0",
        META_WHATSAPP_DEFAULT_TEMPLATE_NAME="hello_world",
        META_WHATSAPP_DEFAULT_TEMPLATE_LANG="en_US",
        META_WHATSAPP_PREFER_TEMPLATE=True,
    )
    @patch("notifications.services.providers.requests.post")
    def test_send_prefers_template_payload_by_default(self, post_mock):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"messages": [{"id": "wamid.template.preferred"}]}
        post_mock.return_value = response

        provider = WhatsappNotificationProvider()
        message_id = provider.send(recipient="+6282237392596", subject="ignored", body="ignored")

        self.assertEqual(message_id, "wamid.template.preferred")
        post_mock.assert_called_once()
        _, kwargs = post_mock.call_args
        self.assertEqual(kwargs["json"]["type"], "template")
        self.assertEqual(kwargs["json"]["template"]["name"], "hello_world")

    @override_settings(
        META_WHATSAPP_ACCESS_TOKEN="expired-token",
        META_PHONE_NUMBER_ID="942804508924296",
        META_GRAPH_API_VERSION="v23.0",
        META_APP_ID="app-id",
        META_APP_SECRET="app-secret",
        META_WHATSAPP_AUTO_REFRESH_ACCESS_TOKEN=True,
    )
    @patch("notifications.services.meta_access_token.requests.get")
    @patch("notifications.services.providers.requests.post")
    def test_send_refreshes_access_token_and_retries_when_meta_returns_token_error(self, post_mock, refresh_get_mock):
        expired_response = Mock()
        expired_response.status_code = 401
        expired_response.text = '{"error":{"type":"OAuthException","code":190}}'
        expired_response.json.return_value = {"error": {"type": "OAuthException", "code": 190}}

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {"messages": [{"id": "wamid.refreshed.token"}]}

        post_mock.side_effect = [expired_response, success_response]

        refresh_response = Mock()
        refresh_response.status_code = 200
        refresh_response.json.return_value = {
            "access_token": "new-meta-token",
            "token_type": "bearer",
            "expires_in": 5183944,
        }
        refresh_get_mock.return_value = refresh_response

        provider = WhatsappNotificationProvider()
        message_id = provider.send(recipient="+6282237392596", subject="ignored", body="Hello from test")

        self.assertEqual(message_id, "wamid.refreshed.token")
        self.assertEqual(post_mock.call_count, 2)
        _, first_kwargs = post_mock.call_args_list[0]
        _, second_kwargs = post_mock.call_args_list[1]
        self.assertEqual(first_kwargs["headers"]["Authorization"], "Bearer expired-token")
        self.assertEqual(second_kwargs["headers"]["Authorization"], "Bearer new-meta-token")
        refresh_get_mock.assert_called_once()

    @override_settings(
        META_WHATSAPP_ACCESS_TOKEN="stale-token",
        META_GRAPH_API_VERSION="v23.0",
        META_APP_ID="app-id",
        META_APP_SECRET="app-secret",
        META_WHATSAPP_AUTO_REFRESH_ACCESS_TOKEN=True,
    )
    @patch("notifications.services.providers.requests.get")
    def test_get_message_status_refreshes_token_and_retries(self, provider_get_mock):
        expired_response = Mock()
        expired_response.status_code = 401
        expired_response.text = '{"error":{"code":190}}'
        expired_response.json.return_value = {"error": {"code": 190}}

        refresh_response = Mock()
        refresh_response.status_code = 200
        refresh_response.json.return_value = {
            "access_token": "fresh-status-token",
            "token_type": "bearer",
            "expires_in": 5183944,
        }

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {"status": "delivered"}
        provider_get_mock.side_effect = [expired_response, refresh_response, success_response]

        provider = WhatsappNotificationProvider()
        result = provider.get_message_status(message_id="wamid.status.token")

        self.assertEqual(result["status"], "delivered")
        self.assertEqual(provider_get_mock.call_count, 3)
        _, first_kwargs = provider_get_mock.call_args_list[0]
        _, refresh_kwargs = provider_get_mock.call_args_list[1]
        _, second_kwargs = provider_get_mock.call_args_list[2]
        self.assertEqual(first_kwargs["headers"]["Authorization"], "Bearer stale-token")
        self.assertIn("/oauth/access_token", provider_get_mock.call_args_list[1].args[0])
        self.assertIn("grant_type", refresh_kwargs["params"])
        self.assertEqual(second_kwargs["headers"]["Authorization"], "Bearer fresh-status-token")


class MetaWebhookSignatureTests(SimpleTestCase):
    @override_settings(META_APP_SECRET="test-secret")
    def test_verify_meta_webhook_signature(self):
        raw_body = b'{"object":"whatsapp_business_account"}'
        import hashlib
        import hmac

        signature = "sha256=" + hmac.new(b"test-secret", raw_body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_meta_webhook_signature(raw_body, signature))
        self.assertFalse(verify_meta_webhook_signature(raw_body, "sha256=invalid"))
