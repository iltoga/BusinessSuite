import json
from datetime import date
from unittest.mock import patch

from core.models import AsyncJob, DocumentOCRJob, OCRJob
from core.services.redis_streams import StreamEvent
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from invoices.models import Invoice, InvoiceDownloadJob, InvoiceImportItem, InvoiceImportJob
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()


class StreamingPerformanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("stream-user", "stream@example.com", "pass")
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")
        self.client.force_authenticate(self.user)

    @staticmethod
    def _decode_sse_payload(chunk) -> dict:
        """Parse a single SSE chunk and return the JSON payload.

        The production helpers guarantee that a "data: " line exists, so
        tests assert that we never return ``None``.  If the payload is
        missing we raise an assertion with the raw chunk to aid debugging.
        """
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8")
        data_line = next((line for line in chunk.splitlines() if line.startswith("data: ")), None)
        assert data_line is not None, f"No data line in SSE chunk: {chunk!r}"
        return json.loads(data_line.replace("data: ", "", 1))

    @patch("api.view_notifications.iter_replay_and_live_events")
    def test_async_job_sse_progress_event_uses_stream_payload_without_db_query(self, iter_events_mock):
        job = AsyncJob.objects.create(
            task_name="export",
            status=AsyncJob.STATUS_PROCESSING,
            progress=5,
            message="Queued",
            created_by=self.user,
        )
        iter_events_mock.return_value = iter(
            [
                StreamEvent(
                    id="1-0",
                    event="async_job_status",
                    status=AsyncJob.STATUS_PROCESSING,
                    timestamp="2026-03-06T10:00:00+00:00",
                    payload={
                        "id": str(job.id),
                        "status": AsyncJob.STATUS_PROCESSING,
                        "progress": 45,
                        "message": "Halfway there",
                        "result": None,
                        "errorMessage": "",
                    },
                    raw={},
                )
            ]
        )

        response = self.client.get(reverse("api-async-job-status-sse", kwargs={"job_id": str(job.id)}))
        self.assertEqual(response.status_code, 200)

        stream = response.streaming_content
        initial_payload = self._decode_sse_payload(next(stream))
        self.assertEqual(initial_payload["progress"], 5)

        with CaptureQueriesContext(connection) as captured:
            progress_payload = self._decode_sse_payload(next(stream))

        self.assertEqual(len(captured), 0)
        self.assertEqual(progress_payload["progress"], 45)
        self.assertEqual(progress_payload["message"], "Halfway there")

    @patch("api.view_notifications.iter_replay_and_live_events")
    def test_async_job_sse_terminal_event_verifies_final_state_from_db(self, iter_events_mock):
        job = AsyncJob.objects.create(
            task_name="export",
            status=AsyncJob.STATUS_PROCESSING,
            progress=5,
            message="Queued",
            created_by=self.user,
        )
        iter_events_mock.return_value = iter(
            [
                StreamEvent(
                    id="2-0",
                    event="async_job_status",
                    status=AsyncJob.STATUS_COMPLETED,
                    timestamp="2026-03-06T10:01:00+00:00",
                    payload={
                        "id": str(job.id),
                        "status": AsyncJob.STATUS_COMPLETED,
                        "progress": 100,
                        "message": "Done",
                        "result": None,
                        "errorMessage": "",
                    },
                    raw={},
                )
            ]
        )

        response = self.client.get(reverse("api-async-job-status-sse", kwargs={"job_id": str(job.id)}))
        stream = response.streaming_content
        _ = next(stream)

        job.complete(result={"downloadUrl": "/final.pdf"}, message="Completed")

        with CaptureQueriesContext(connection) as captured:
            terminal_payload = self._decode_sse_payload(next(stream))

        self.assertGreaterEqual(len(captured), 1)
        self.assertEqual(terminal_payload["status"], AsyncJob.STATUS_COMPLETED)
        self.assertEqual(terminal_payload["result"], {"downloadUrl": "/final.pdf"})
        self.assertEqual(terminal_payload["message"], "Completed")

    @patch("api.view_applications.iter_replay_and_live_events")
    def test_ocr_stream_progress_event_uses_stream_payload_without_db_query(self, iter_events_mock):
        job = OCRJob.objects.create(
            status=OCRJob.STATUS_PROCESSING,
            progress=5,
            file_path="tmpfiles/passport.png",
            file_url="/uploads/tmpfiles/passport.png",
            created_by=self.user,
        )
        iter_events_mock.return_value = iter(
            [
                StreamEvent(
                    id="2-1",
                    event="ocr_job_changed",
                    status=OCRJob.STATUS_PROCESSING,
                    timestamp="2026-03-06T10:01:30+00:00",
                    payload={
                        "jobId": str(job.id),
                        "status": OCRJob.STATUS_PROCESSING,
                        "progress": 63,
                        "errorMessage": "",
                    },
                    raw={},
                )
            ]
        )

        response = self.client.get(reverse("api-ocr-stream", kwargs={"job_id": str(job.id)}))
        self.assertEqual(response.status_code, 200)

        stream = response.streaming_content
        initial_payload = self._decode_sse_payload(next(stream))
        self.assertEqual(initial_payload["progress"], 5)

        with CaptureQueriesContext(connection) as captured:
            progress_payload = self._decode_sse_payload(next(stream))

        self.assertEqual(len(captured), 0)
        self.assertEqual(progress_payload["progress"], 63)
        self.assertEqual(progress_payload["status"], OCRJob.STATUS_PROCESSING)

    @patch("api.view_applications.iter_replay_and_live_events")
    def test_document_ocr_stream_progress_event_uses_stream_payload_without_db_query(self, iter_events_mock):
        job = DocumentOCRJob.objects.create(
            status=DocumentOCRJob.STATUS_PROCESSING,
            progress=12,
            file_path="tmpfiles/document.pdf",
            file_url="/uploads/tmpfiles/document.pdf",
            created_by=self.user,
        )
        iter_events_mock.return_value = iter(
            [
                StreamEvent(
                    id="2-2",
                    event="document_ocr_job_changed",
                    status=DocumentOCRJob.STATUS_PROCESSING,
                    timestamp="2026-03-06T10:01:45+00:00",
                    payload={
                        "jobId": str(job.id),
                        "status": DocumentOCRJob.STATUS_PROCESSING,
                        "progress": 71,
                        "errorMessage": "",
                    },
                    raw={},
                )
            ]
        )

        response = self.client.get(reverse("api-document-ocr-stream", kwargs={"job_id": str(job.id)}))
        self.assertEqual(response.status_code, 200)

        stream = response.streaming_content
        initial_payload = self._decode_sse_payload(next(stream))
        self.assertEqual(initial_payload["progress"], 12)

        with CaptureQueriesContext(connection) as captured:
            progress_payload = self._decode_sse_payload(next(stream))

        self.assertEqual(len(captured), 0)
        self.assertEqual(progress_payload["progress"], 71)
        self.assertEqual(progress_payload["status"], DocumentOCRJob.STATUS_PROCESSING)

    @patch("api.view_billing.iter_replay_and_live_events")
    def test_invoice_download_stream_progress_event_uses_stream_payload_without_db_query(self, iter_events_mock):
        customer = Customer.objects.create(first_name="Download", last_name="Owner")
        invoice = Invoice.objects.create(
            customer=customer,
            invoice_date=date.today(),
            due_date=date.today(),
            created_by=self.user,
            updated_by=self.user,
        )
        job = InvoiceDownloadJob.objects.create(
            invoice=invoice,
            status=InvoiceDownloadJob.STATUS_QUEUED,
            progress=0,
            created_by=self.user,
        )
        iter_events_mock.return_value = iter(
            [
                StreamEvent(
                    id="3-0",
                    event="invoice_download_job_changed",
                    status=InvoiceDownloadJob.STATUS_PROCESSING,
                    timestamp="2026-03-06T10:02:00+00:00",
                    payload={
                        "jobId": str(job.id),
                        "status": InvoiceDownloadJob.STATUS_PROCESSING,
                        "progress": 60,
                        "errorMessage": "",
                    },
                    raw={},
                )
            ]
        )

        response = self.client.get(reverse("invoices-download-async-stream", kwargs={"job_id": str(job.id)}))
        self.assertEqual(response.status_code, 200)

        stream = response.streaming_content
        self.assertEqual(self._decode_sse_payload(next(stream))["message"], "Starting invoice generation...")
        self.assertEqual(self._decode_sse_payload(next(stream))["progress"], 0)

        with CaptureQueriesContext(connection) as captured:
            progress_payload = self._decode_sse_payload(next(stream))

        self.assertEqual(len(captured), 0)
        self.assertEqual(progress_payload["progress"], 60)
        self.assertEqual(progress_payload["status"], InvoiceDownloadJob.STATUS_PROCESSING)

    @patch("api.view_billing.iter_replay_and_live_events")
    def test_invoice_import_stream_item_event_uses_stream_payload_without_db_query(self, iter_events_mock):
        job = InvoiceImportJob.objects.create(
            status=InvoiceImportJob.STATUS_PROCESSING,
            progress=0,
            total_files=1,
            created_by=self.user,
        )
        item = InvoiceImportItem.objects.create(
            job=job,
            sort_index=1,
            filename="invoice.pdf",
            file_path="tmpfiles/invoice.pdf",
            status=InvoiceImportItem.STATUS_QUEUED,
        )
        iter_events_mock.return_value = iter(
            [
                StreamEvent(
                    id="4-0",
                    event="invoice_import_item_changed",
                    status=InvoiceImportItem.STATUS_PROCESSING,
                    timestamp="2026-03-06T10:03:00+00:00",
                    payload={
                        "itemId": str(item.id),
                        "jobId": str(job.id),
                        "index": 1,
                        "filename": "invoice.pdf",
                        "status": InvoiceImportItem.STATUS_PROCESSING,
                        "result": {"stage": "parsing"},
                        "errorMessage": "",
                    },
                    raw={},
                )
            ]
        )

        response = self.client.get(f"/api/invoices/import/stream/{job.id}/")
        self.assertEqual(response.status_code, 200)

        stream = response.streaming_content
        start_payload = self._decode_sse_payload(next(stream))
        self.assertEqual(start_payload["total"], 1)

        with CaptureQueriesContext(connection) as captured:
            event_payload = self._decode_sse_payload(next(stream))

        self.assertEqual(len(captured), 0)
        self.assertEqual(event_payload["filename"], "invoice.pdf")
        self.assertEqual(event_payload["index"], 1)
        self.assertIn("Processing invoice.pdf", event_payload["message"])
