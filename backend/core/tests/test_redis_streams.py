"""Tests for Redis stream publishing and consumption helpers."""

from unittest.mock import MagicMock, patch

from core.services.redis_streams import read_stream_blocking
from django.test import SimpleTestCase


class RedisStreamsServiceTests(SimpleTestCase):
    @patch("core.services.redis_streams.get_redis_client")
    def test_read_stream_blocking_uses_socket_timeout_longer_than_block_window(self, get_redis_client_mock):
        client = MagicMock()
        client.xread.return_value = []
        get_redis_client_mock.return_value = client

        read_stream_blocking(
            "stream:user:42",
            last_event_id=None,
            block_ms=15_000,
            count=123,
        )

        get_redis_client_mock.assert_called_once_with(socket_timeout=20.0)
        client.xread.assert_called_once_with(streams={"stream:user:42": "$"}, block=15_000, count=123)

    @patch("core.services.redis_streams.get_redis_client")
    def test_read_stream_blocking_parses_stream_events(self, get_redis_client_mock):
        client = MagicMock()
        client.xread.return_value = [
            (
                b"stream:user:42",
                [
                    (
                        b"1740812300000-0",
                        {
                            b"event": b"backup_message",
                            b"status": b"info",
                            b"timestamp": b"2026-03-01T00:00:00+00:00",
                            b"payload": b'{"message":"Backup started"}',
                        },
                    )
                ],
            )
        ]
        get_redis_client_mock.return_value = client

        events = read_stream_blocking(
            "stream:user:42",
            last_event_id="1740812200000-0",
            block_ms=10_000,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].id, "1740812300000-0")
        self.assertEqual(events[0].event, "backup_message")
        self.assertEqual(events[0].status, "info")
        self.assertEqual(events[0].payload, {"message": "Backup started"})
