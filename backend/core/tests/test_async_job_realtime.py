from unittest.mock import patch

from core.models import AsyncJob
from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class AsyncJobRealtimeSignalTests(TestCase):
    @patch("core.signals_streams.RealtimeEventDispatcherService.publish_job_update")
    @patch("core.signals_streams._publish_stream_event_safe")
    def test_async_job_updates_are_broadcast_to_job_and_user_streams(
        self,
        publish_stream_mock,
        publish_job_update_mock,
    ):
        user = User.objects.create_user("async-owner", "async-owner@example.com", "pass")

        job = AsyncJob.objects.create(
            task_name="check_passport_uploadability",
            status=AsyncJob.STATUS_PENDING,
            message="Queued passport verification...",
            created_by=user,
        )

        job.update_progress(25, "Reading passport image...", AsyncJob.STATUS_PROCESSING)

        publish_stream_mock.assert_called()
        publish_job_update_mock.assert_called()

        last_user_stream_call = publish_job_update_mock.call_args_list[-1]
        self.assertEqual(last_user_stream_call.kwargs["user_id"], user.id)
        self.assertEqual(last_user_stream_call.kwargs["job_id"], str(job.id))
        self.assertEqual(last_user_stream_call.kwargs["status"], AsyncJob.STATUS_PROCESSING)
        self.assertEqual(last_user_stream_call.kwargs["progress"], 25)
        self.assertEqual(last_user_stream_call.kwargs["payload"]["message"], "Reading passport image...")
