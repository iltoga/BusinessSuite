import json
import signal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings


class _FakeResponse:
    def __init__(self, *, status_code=200, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            return {}
        return self._payload


@override_settings(
    META_APP_ID="app-123",
    META_APP_SECRET="app-secret-456",
    META_TOKEN_CLIENT="verify-token-789",
    META_GRAPH_API_VERSION="v23.0",
)
class WhatsappWebhookTunnelCommandTests(SimpleTestCase):
    @patch("core.management.commands.whatsapp_webhook_tunnel.requests.post")
    @patch("core.management.commands.whatsapp_webhook_tunnel.requests.get")
    def test_start_with_callback_url_switches_subscription_and_writes_state(self, get_mock, post_mock):
        with TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "wa_state.json"
            subscription_payload = {
                "data": [
                    {
                        "object": "whatsapp_business_account",
                        "callback_url": "https://crm.revisbali.com/api/notifications/whatsapp/webhook/",
                        "fields": [
                            {"name": "messages", "version": "v24.0"},
                            {"name": "account_update", "version": "v24.0"},
                        ],
                    }
                ]
            }
            get_mock.side_effect = [
                _FakeResponse(status_code=200, payload=subscription_payload, text=json.dumps(subscription_payload)),
                _FakeResponse(status_code=200, text="webhook-check"),
            ]
            post_mock.return_value = _FakeResponse(status_code=200, payload={"success": True}, text='{"success":true}')

            stdout = StringIO()
            call_command(
                "whatsapp_webhook_tunnel",
                "start",
                "--callback-url",
                "https://demo.ngrok-free.app",
                "--state-file",
                str(state_file),
                stdout=stdout,
            )

            self.assertTrue(state_file.exists())
            state = json.loads(state_file.read_text())
            self.assertEqual(
                state["old_callback_url"],
                "https://crm.revisbali.com/api/notifications/whatsapp/webhook/",
            )
            self.assertEqual(
                state["new_callback_url"],
                "https://demo.ngrok-free.app/api/notifications/whatsapp/webhook/",
            )
            self.assertIsNone(state["ngrok_pid"])

            post_kwargs = post_mock.call_args.kwargs
            self.assertEqual(
                post_kwargs["data"]["callback_url"],
                "https://demo.ngrok-free.app/api/notifications/whatsapp/webhook/",
            )
            self.assertEqual(post_kwargs["data"]["fields"], "messages,account_update")

    @patch("core.management.commands.whatsapp_webhook_tunnel.os.kill")
    @patch("core.management.commands.whatsapp_webhook_tunnel.requests.post")
    def test_stop_restores_callback_and_terminates_ngrok(self, post_mock, kill_mock):
        with TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "wa_state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "old_callback_url": "https://crm.revisbali.com/api/notifications/whatsapp/webhook/",
                        "new_callback_url": "https://demo.ngrok-free.app/api/notifications/whatsapp/webhook/",
                        "fields": ["messages", "account_update"],
                        "ngrok_pid": 4242,
                    }
                )
            )
            post_mock.return_value = _FakeResponse(status_code=200, payload={"success": True}, text='{"success":true}')

            call_command(
                "whatsapp_webhook_tunnel",
                "stop",
                "--state-file",
                str(state_file),
            )

            post_kwargs = post_mock.call_args.kwargs
            self.assertEqual(
                post_kwargs["data"]["callback_url"],
                "https://crm.revisbali.com/api/notifications/whatsapp/webhook/",
            )
            self.assertEqual(post_kwargs["data"]["fields"], "messages,account_update")
            kill_mock.assert_called_once_with(4242, signal.SIGTERM)
            self.assertFalse(state_file.exists())
