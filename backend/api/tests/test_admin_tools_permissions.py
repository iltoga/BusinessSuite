import asyncio
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.permissions import SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR

User = get_user_model()


def _async_iter(*items):
    """Wrap items as an async iterable — required for mocking async-for streams."""

    async def _gen():
        for item in items:
            yield item

    return _gen()


async def _consume_async_stream(response):
    """Exhaust an async streaming response content generator."""
    chunks = []
    async for chunk in response.streaming_content:
        chunks.append(chunk)
    return chunks


class AdminToolsPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_group = Group.objects.create(name="admin")
        self.admin_group_user = User.objects.create_user("backup-admin", "backup-admin@example.com", "pass")
        self.admin_group_user.groups.add(self.admin_group)
        self.regular_user = User.objects.create_user("backup-user", "backup-user@example.com", "pass")

    @patch("api.views_admin.admin_tasks.run_backup_stream.delay")
    def test_backup_start_sse_allows_admin_group_user(self, enqueue_mock):
        token = Token.objects.create(user=self.admin_group_user)

        response = self.client.get("/api/backups/start/", HTTP_AUTHORIZATION=f"Token {token.key}")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get("Content-Type", "").startswith("text/event-stream"))
        enqueue_mock.assert_not_called()

    @patch("api.views_admin.iter_replay_and_live_events_async")
    @patch("api.views_admin.admin_tasks.run_backup_stream.delay")
    def test_backup_start_sse_enqueues_even_when_last_event_id_header_is_present(self, enqueue_mock, stream_iter_mock):
        token = Token.objects.create(user=self.admin_group_user)
        stream_iter_mock.return_value = _async_iter(None)

        response = self.client.get(
            "/api/backups/start/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
            HTTP_LAST_EVENT_ID="1-0",
        )

        asyncio.run(_consume_async_stream(response))
        enqueue_mock.assert_called_once()

    @patch("api.views_admin.iter_replay_and_live_events_async")
    @patch("api.views_admin.admin_tasks.run_backup_stream.delay")
    def test_backup_start_sse_replay_mode_does_not_enqueue_new_job(self, enqueue_mock, stream_iter_mock):
        token = Token.objects.create(user=self.admin_group_user)
        stream_iter_mock.return_value = _async_iter()

        response = self.client.get(
            "/api/backups/start/?replay=1",
            HTTP_AUTHORIZATION=f"Token {token.key}",
            HTTP_LAST_EVENT_ID="1-0",
        )

        asyncio.run(_consume_async_stream(response))
        enqueue_mock.assert_not_called()

    def test_backup_start_sse_rejects_non_admin_user(self):
        token = Token.objects.create(user=self.regular_user)

        response = self.client.get("/api/backups/start/", HTTP_AUTHORIZATION=f"Token {token.key}")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR)
