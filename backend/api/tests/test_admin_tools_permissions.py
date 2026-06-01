"""Regression tests for admin tools permission checks."""

from unittest.mock import patch

from api.permissions import SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR
from core.services.redis_streams import StreamEvent
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()


def _sync_iter(*items):
    """Wrap items as a sync iterable — required for mocking sync-for streams."""

    def _gen():
        for item in items:
            yield item

    return _gen()


def _consume_stream(response):
    """Exhaust a streaming response content generator."""
    chunks = []
    for chunk in response.streaming_content:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(chunk)
    return chunks


class AdminToolsPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        cache.clear()
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

    @patch("api.views_admin.iter_replay_and_live_events")
    @patch("api.views_admin.admin_tasks.run_backup_stream.delay")
    def test_backup_start_sse_enqueues_even_when_last_event_id_header_is_present(self, enqueue_mock, stream_iter_mock):
        token = Token.objects.create(user=self.admin_group_user)
        stream_iter_mock.return_value = _sync_iter(None)

        response = self.client.get(
            "/api/backups/start/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
            HTTP_LAST_EVENT_ID="1-0",
        )

        _consume_stream(response)
        enqueue_mock.assert_called_once()

    @patch("api.views_admin.iter_replay_and_live_events")
    @patch("api.views_admin.admin_tasks.run_backup_stream.delay")
    def test_backup_start_sse_replay_mode_does_not_enqueue_new_job(self, enqueue_mock, stream_iter_mock):
        token = Token.objects.create(user=self.admin_group_user)
        stream_iter_mock.return_value = _sync_iter()

        response = self.client.get(
            "/api/backups/start/?replay=1",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

        _consume_stream(response)
        enqueue_mock.assert_not_called()
        self.assertEqual(stream_iter_mock.call_args.kwargs["last_event_id"], "0-0")

    @patch("api.views_admin.iter_replay_and_live_events")
    @patch("api.views_admin.admin_tasks.run_backup_stream.delay")
    def test_backup_start_sse_is_idempotent_for_same_key(self, enqueue_mock, stream_iter_mock):
        token = Token.objects.create(user=self.admin_group_user)
        stream_iter_mock.return_value = _sync_iter()

        first_response = self.client.get(
            "/api/backups/start/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
            HTTP_IDEMPOTENCY_KEY="backup-start-1",
        )
        second_response = self.client.get(
            "/api/backups/start/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
            HTTP_IDEMPOTENCY_KEY="backup-start-1",
        )

        _consume_stream(first_response)
        _consume_stream(second_response)

        self.assertEqual(enqueue_mock.call_count, 1)

    @patch("api.views_admin.iter_replay_and_live_events")
    def test_backup_start_sse_filters_events_by_job_id(self, stream_iter_mock):
        token = Token.objects.create(user=self.admin_group_user)
        stream_iter_mock.return_value = _sync_iter(
            StreamEvent(
                id="1-0",
                event="backup_message",
                status="info",
                timestamp="2026-05-30T10:00:00+00:00",
                payload={"jobId": "job-other", "message": "other job"},
                raw={"job_id": "job-other"},
            ),
            StreamEvent(
                id="2-0",
                event="backup_finished",
                status="success",
                timestamp="2026-05-30T10:00:01+00:00",
                payload={
                    "jobId": "job-target",
                    "message": "target job",
                    "requestId": "req-target-1",
                    "_terminal": True,
                },
                raw={"job_id": "job-target", "correlation_id": "req-target-1"},
            ),
        )

        response = self.client.get(
            "/api/backups/start/?replay=1&job_id=job-target",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

        body = "".join(_consume_stream(response))
        self.assertIn('"jobId": "job-target"', body)
        self.assertIn('"message": "target job"', body)
        self.assertIn('"requestId": "req-target-1"', body)
        self.assertNotIn('"jobId": "job-other"', body)

    @patch("api.views_admin.admin_tasks.run_backup_stream.delay")
    def test_backup_start_job_returns_202_contract(self, enqueue_mock):
        self.client.force_authenticate(user=self.admin_group_user)

        response = self.client.post(
            "/api/backups/start-job/?include_users=1",
            HTTP_X_REQUEST_ID="req-backup-start-1",
            HTTP_IDEMPOTENCY_KEY="backup-start-job-1",
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["progress"], 0)
        self.assertTrue(payload["queued"])
        self.assertFalse(payload["deduplicated"])
        self.assertEqual(payload["requestId"], "req-backup-start-1")
        self.assertIn("jobId", payload)
        self.assertTrue(payload["streamUrl"].endswith(f"/api/backups/start/?replay=1&job_id={payload['jobId']}"))
        enqueue_mock.assert_called_once_with(
            user_id=self.admin_group_user.id,
            include_users=True,
            job_id=payload["jobId"],
            request_id="req-backup-start-1",
        )

    @patch("api.views_admin.admin_tasks.run_backup_stream.delay")
    def test_backup_start_job_is_deduplicated_for_same_key(self, enqueue_mock):
        self.client.force_authenticate(user=self.admin_group_user)

        first = self.client.post(
            "/api/backups/start-job/?include_users=1",
            HTTP_X_REQUEST_ID="req-backup-start-1",
            HTTP_IDEMPOTENCY_KEY="backup-start-job-1",
        )
        second = self.client.post(
            "/api/backups/start-job/?include_users=1",
            HTTP_X_REQUEST_ID="req-backup-start-2",
            HTTP_IDEMPOTENCY_KEY="backup-start-job-1",
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.json()["jobId"], first.json()["jobId"])
        self.assertTrue(second.json()["deduplicated"])
        self.assertFalse(second.json()["queued"])
        self.assertEqual(enqueue_mock.call_count, 1)

    @patch("api.views_admin.admin_tasks.run_backup_stream.delay")
    def test_backup_start_job_returns_409_on_idempotency_conflict(self, enqueue_mock):
        self.client.force_authenticate(user=self.admin_group_user)

        first = self.client.post(
            "/api/backups/start-job/?include_users=1",
            HTTP_X_REQUEST_ID="req-backup-start-1",
            HTTP_IDEMPOTENCY_KEY="backup-start-job-1",
        )
        second = self.client.post(
            "/api/backups/start-job/?include_users=0",
            HTTP_X_REQUEST_ID="req-backup-start-2",
            HTTP_IDEMPOTENCY_KEY="backup-start-job-1",
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"]["code"], "conflict")
        self.assertEqual(enqueue_mock.call_count, 1)

    @patch("api.views_admin._resolve_backup_path", return_value="/tmp/backup-20260530.tar.zst")
    @patch("api.views_admin.admin_tasks.run_restore_stream.delay")
    def test_backup_restore_job_returns_202_contract(self, enqueue_mock, _resolve_backup_path_mock):
        self.client.force_authenticate(user=self.admin_group_user)

        response = self.client.post(
            "/api/backups/restore-job/?file=backup-20260530.tar.zst&include_users=1",
            HTTP_X_REQUEST_ID="req-backup-restore-1",
            HTTP_IDEMPOTENCY_KEY="backup-restore-job-1",
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["progress"], 0)
        self.assertFalse(payload["deduplicated"])
        self.assertEqual(payload["requestId"], "req-backup-restore-1")
        self.assertIn("jobId", payload)
        self.assertTrue(payload["streamUrl"].endswith(f"/api/backups/restore/?replay=1&job_id={payload['jobId']}"))
        enqueue_mock.assert_called_once_with(
            user_id=self.admin_group_user.id,
            archive_path="/tmp/backup-20260530.tar.zst",
            include_users=True,
            job_id=payload["jobId"],
            request_id="req-backup-restore-1",
        )

    def test_backup_start_sse_rejects_non_admin_user(self):
        token = Token.objects.create(user=self.regular_user)

        response = self.client.get("/api/backups/start/", HTTP_AUTHORIZATION=f"Token {token.key}")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "forbidden")
        self.assertEqual(response.json()["error"]["message"], SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR)
