"""Regression tests for realtime SSE streaming endpoints."""

from unittest.mock import patch

from api.tests.async_iter_helper import SyncAsyncIter
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()


class RealtimeStreamSseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("realtime-user", "realtime@example.com", "pass")
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")

    @staticmethod
    def _decode_chunk(chunk) -> str:
        if isinstance(chunk, bytes):
            return chunk.decode("utf-8")
        return chunk

    @patch("api.view_realtime.iter_replay_and_live_events_async")
    def test_realtime_stream_sse_yields_connected_event_and_keepalive(self, iter_events_mock):
        async def _mock_events():
            yield None

        iter_events_mock.return_value = _mock_events()
        response = self.client.get("/api/core/realtime/stream/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")

        stream = SyncAsyncIter(response.streaming_content)
        try:
            first_chunk = self._decode_chunk(next(stream))
            second_chunk = self._decode_chunk(next(stream))
        finally:
            stream.close()

        self.assertIn('"event": "connected"', first_chunk)
        self.assertIn(f'"userId": {self.user.id}', first_chunk)
        self.assertEqual(second_chunk, ": keepalive\n\n")
        iter_events_mock.assert_called_once()
