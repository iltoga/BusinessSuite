"""Regression tests for admin async stream task publication."""

from unittest.mock import patch

from admin_tools import tasks
from django.test import SimpleTestCase


class AdminStreamTaskTests(SimpleTestCase):
    @patch("admin_tools.tasks.publish_stream_event", return_value="1-0")
    def test_publish_user_event_propagates_job_and_request_ids(self, publish_stream_event_mock):
        tasks._publish_user_event(
            42,
            event="backup_started",
            status="info",
            payload={"message": "Backup started"},
            job_id="job-42",
            request_id="req-42",
        )

        publish_stream_event_mock.assert_called_once_with(
            "stream:user:42",
            event="backup_started",
            status="info",
            payload={
                "message": "Backup started",
                "jobId": "job-42",
                "requestId": "req-42",
            },
            job_id="job-42",
            user_id="42",
            correlation_id="req-42",
        )

    @patch("admin_tools.tasks.publish_stream_event", return_value="2-0")
    @patch("admin_tools.tasks.services.backup_all", return_value=iter(["RESULT_PATH:/tmp/backup.tar.zst"]))
    def test_run_backup_stream_emits_request_id_in_start_and_finish_events(
        self,
        _backup_all_mock,
        publish_stream_event_mock,
    ):
        tasks.run_backup_stream.call_local(
            user_id=7,
            include_users=True,
            job_id="job-backup-7",
            request_id="req-backup-7",
        )

        self.assertEqual(publish_stream_event_mock.call_count, 2)
        start_call = publish_stream_event_mock.call_args_list[0]
        finish_call = publish_stream_event_mock.call_args_list[1]

        self.assertEqual(start_call.kwargs["event"], "backup_started")
        self.assertEqual(start_call.kwargs["correlation_id"], "req-backup-7")
        self.assertEqual(start_call.kwargs["payload"]["requestId"], "req-backup-7")
        self.assertEqual(start_call.kwargs["payload"]["jobId"], "job-backup-7")

        self.assertEqual(finish_call.kwargs["event"], "backup_finished")
        self.assertEqual(finish_call.kwargs["correlation_id"], "req-backup-7")
        self.assertEqual(finish_call.kwargs["payload"]["requestId"], "req-backup-7")
        self.assertEqual(finish_call.kwargs["payload"]["jobId"], "job-backup-7")
        self.assertEqual(finish_call.kwargs["payload"]["resultPath"], "/tmp/backup.tar.zst")

    @patch("admin_tools.tasks.publish_stream_event", return_value="3-0")
    @patch("admin_tools.tasks.services.cleanup_unlinked_media_files")
    def test_media_cleanup_failure_event_preserves_request_id(
        self,
        cleanup_unlinked_media_files_mock,
        publish_stream_event_mock,
    ):
        cleanup_unlinked_media_files_mock.side_effect = RuntimeError("cleanup exploded")

        tasks.run_media_cleanup_stream.call_local(
            user_id=11,
            dry_run=False,
            job_id="job-cleanup-11",
            request_id="req-cleanup-11",
        )

        failure_call = publish_stream_event_mock.call_args_list[-1]
        self.assertEqual(failure_call.kwargs["event"], "media_cleanup_failed")
        self.assertEqual(failure_call.kwargs["correlation_id"], "req-cleanup-11")
        self.assertEqual(failure_call.kwargs["payload"]["requestId"], "req-cleanup-11")
        self.assertEqual(failure_call.kwargs["payload"]["jobId"], "job-cleanup-11")
        self.assertEqual(failure_call.kwargs["payload"]["error"], "cleanup exploded")
