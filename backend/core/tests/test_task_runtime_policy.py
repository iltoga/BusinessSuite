"""Tests for task runtime policy evaluation helpers."""

from unittest.mock import patch

import dramatiq
from core.tasks.calendar_reminders import dispatch_due_calendar_reminders_periodic_task
from core.tasks.calendar_sync import create_google_event_task
from core.tasks.runtime import (
    QUEUE_DEFAULT,
    QUEUE_DOC_CONVERSION,
    QUEUE_REALTIME,
    QUEUE_SCHEDULED,
    db_task,
    retry_on_transient_external_failure,
)
from customers.tasks import check_passport_uploadability_task
from django.test import SimpleTestCase
from invoices.tasks.download_jobs import run_invoice_download_job
from invoices.tasks.import_jobs import run_invoice_import_item


class TaskRuntimePolicyTests(SimpleTestCase):
    def test_queue_defaults_are_applied_to_realtime_tasks(self):
        @db_task(queue=QUEUE_REALTIME, queue_defaults=True, retry_when=retry_on_transient_external_failure)
        def sample_task() -> None:
            return None

        self.assertEqual(sample_task.actor.queue_name, QUEUE_REALTIME)
        self.assertEqual(sample_task.actor.options.get("max_retries"), 2)
        self.assertEqual(sample_task.actor.options.get("min_backoff"), 10_000)
        self.assertEqual(sample_task.actor.options.get("max_backoff"), 45_000)
        self.assertEqual(sample_task.actor.options.get("time_limit"), 150_000)

    def test_queue_defaults_are_applied_to_document_conversion_tasks(self):
        @db_task(queue=QUEUE_DOC_CONVERSION, queue_defaults=True, retry_when=retry_on_transient_external_failure)
        def sample_doc_task() -> None:
            return None

        self.assertEqual(sample_doc_task.actor.queue_name, QUEUE_DOC_CONVERSION)
        self.assertEqual(sample_doc_task.actor.options.get("max_retries"), 3)
        self.assertEqual(sample_doc_task.actor.options.get("min_backoff"), 15_000)
        self.assertEqual(sample_doc_task.actor.options.get("max_backoff"), 180_000)
        self.assertEqual(sample_doc_task.actor.options.get("time_limit"), 420_000)

    def test_queue_defaults_are_applied_to_scheduled_tasks(self):
        @db_task(queue=QUEUE_SCHEDULED, queue_defaults=True)
        def sample_scheduled_task() -> None:
            return None

        self.assertEqual(sample_scheduled_task.actor.queue_name, QUEUE_SCHEDULED)
        self.assertEqual(sample_scheduled_task.actor.options.get("max_retries"), 1)
        self.assertEqual(sample_scheduled_task.actor.options.get("min_backoff"), 30_000)
        self.assertEqual(sample_scheduled_task.actor.options.get("max_backoff"), 120_000)
        self.assertEqual(sample_scheduled_task.actor.options.get("time_limit"), 300_000)

    def test_user_visible_actors_opt_into_queue_defaults(self):
        expected = (
            (check_passport_uploadability_task, QUEUE_REALTIME, 2, 150_000),
            (run_invoice_import_item, QUEUE_REALTIME, 2, 150_000),
            (run_invoice_download_job, QUEUE_DOC_CONVERSION, 3, 420_000),
            (create_google_event_task, QUEUE_DEFAULT, 3, 300_000),
            (dispatch_due_calendar_reminders_periodic_task, QUEUE_SCHEDULED, 1, 300_000),
        )

        for task, queue_name, retries, time_limit in expected:
            with self.subTest(actor=task.actor.actor_name):
                self.assertEqual(task.actor.queue_name, queue_name)
                self.assertEqual(task.actor.options.get("max_retries"), retries)
                self.assertEqual(task.actor.options.get("time_limit"), time_limit)

    def test_retryable_exception_is_wrapped_in_retry_with_custom_jitter(self):
        @db_task(
            retries=2,
            retry_delay=10,
            max_backoff_ms=30_000,
            retry_jitter_ms=2_000,
            retry_when=retry_on_transient_external_failure,
        )
        def flaky_task() -> None:
            raise TimeoutError("temporary upstream timeout")

        with patch("core.tasks.runtime.random.randint", return_value=11_234):
            with self.assertRaises(dramatiq.Retry) as raised:
                flaky_task.actor.fn()

        self.assertEqual(raised.exception.delay, 11_234)

    def test_non_retryable_exception_bubbles_without_retry_wrapping(self):
        @db_task(
            retries=2,
            retry_delay=10,
            max_backoff_ms=30_000,
            retry_jitter_ms=2_000,
            retry_when=retry_on_transient_external_failure,
        )
        def invalid_task() -> None:
            raise ValueError("bad payload")

        with self.assertRaises(ValueError):
            invalid_task.actor.fn()
