from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from invoices.models import Invoice, InvoiceDownloadJob
from invoices.tasks.download_jobs import run_invoice_download_job

User = get_user_model()


def _run_task(task, **kwargs):
    if hasattr(task, "call_local"):
        return task.call_local(**kwargs)
    if hasattr(task, "func"):
        return task.func(**kwargs)
    return task(**kwargs)


class InvoiceDownloadJobStateCleanupTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="download-job-user", password="testpass")
        self.customer = Customer.objects.create(first_name="Download", last_name="Job")
        self.invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=7),
            created_by=self.user,
        )

    def test_download_job_success_clears_stale_error_fields(self):
        job = InvoiceDownloadJob.objects.create(
            invoice=self.invoice,
            status=InvoiceDownloadJob.STATUS_QUEUED,
            format_type=InvoiceDownloadJob.FORMAT_DOCX,
            error_message="old error",
            traceback="old traceback",
            created_by=self.user,
        )

        class SuccessfulInvoiceService:
            def __init__(self, invoice):
                self.invoice = invoice

            def generate_invoice_data(self):
                return ({"invoice_no": self.invoice.invoice_no_display}, [])

            def generate_invoice_document(self, *args, **kwargs):
                return BytesIO(b"doc-content")

            def generate_partial_invoice_data(self):
                return ({"invoice_no": self.invoice.invoice_no_display}, [], [])

        with (
            patch("invoices.tasks.download_jobs.acquire_task_lock", return_value="token-dl-ok"),
            patch("invoices.tasks.download_jobs.release_task_lock"),
            patch("invoices.tasks.download_jobs.InvoiceService", SuccessfulInvoiceService),
            patch(
                "invoices.tasks.download_jobs.default_storage.save",
                return_value="tmpfiles/invoice_downloads/success.docx",
            ),
        ):
            _run_task(run_invoice_download_job, job_id=str(job.id))

        job.refresh_from_db()
        self.assertEqual(job.status, InvoiceDownloadJob.STATUS_COMPLETED)
        self.assertEqual(job.output_path, "tmpfiles/invoice_downloads/success.docx")
        self.assertEqual(job.error_message, "")
        self.assertEqual(job.traceback, "")
        self.assertEqual(job.progress, 100)

    def test_download_job_failure_clears_stale_output_path(self):
        job = InvoiceDownloadJob.objects.create(
            invoice=self.invoice,
            status=InvoiceDownloadJob.STATUS_QUEUED,
            format_type=InvoiceDownloadJob.FORMAT_DOCX,
            output_path="tmpfiles/invoice_downloads/stale.docx",
            created_by=self.user,
        )

        class FailingInvoiceService:
            def __init__(self, invoice):
                self.invoice = invoice

            def generate_invoice_data(self):
                raise RuntimeError("simulated download failure")

            def generate_invoice_document(self, *args, **kwargs):
                return BytesIO(b"unused")

            def generate_partial_invoice_data(self):
                raise RuntimeError("simulated download failure")

        with (
            patch("invoices.tasks.download_jobs.acquire_task_lock", return_value="token-dl-fail"),
            patch("invoices.tasks.download_jobs.release_task_lock"),
            patch("invoices.tasks.download_jobs.InvoiceService", FailingInvoiceService),
        ):
            _run_task(run_invoice_download_job, job_id=str(job.id))

        job.refresh_from_db()
        self.assertEqual(job.status, InvoiceDownloadJob.STATUS_FAILED)
        self.assertEqual(job.output_path, "")
        self.assertIn("simulated download failure", job.error_message)
        self.assertTrue(job.traceback)
        self.assertEqual(job.progress, 100)
