from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from invoices.models import Invoice, InvoiceDocumentItem, InvoiceDocumentJob, InvoiceImportItem, InvoiceImportJob
from invoices.tasks.document_jobs import run_invoice_document_job
from invoices.tasks.import_jobs import _update_invoice_import_job_counts, run_invoice_import_item

User = get_user_model()


def _run_huey_task(task, **kwargs):
    if hasattr(task, "call_local"):
        return task.call_local(**kwargs)
    if hasattr(task, "func"):
        return task.func(**kwargs)
    return task(**kwargs)


class InvoiceImportJobStatusAggregationTest(TestCase):
    def test_import_job_with_zero_total_files_is_completed(self):
        job = InvoiceImportJob.objects.create(
            status=InvoiceImportJob.STATUS_PROCESSING,
            total_files=3,
            processed_files=2,
            imported_count=1,
            duplicate_count=1,
            error_count=0,
        )

        _update_invoice_import_job_counts(job.id)

        job.refresh_from_db()
        self.assertEqual(job.total_files, 0)
        self.assertEqual(job.processed_files, 0)
        self.assertEqual(job.imported_count, 0)
        self.assertEqual(job.duplicate_count, 0)
        self.assertEqual(job.error_count, 0)
        self.assertEqual(job.status, InvoiceImportJob.STATUS_COMPLETED)
        self.assertEqual(job.progress, 100)

    def test_import_job_syncs_total_files_to_actual_item_count(self):
        job = InvoiceImportJob.objects.create(status=InvoiceImportJob.STATUS_PROCESSING, total_files=99)
        InvoiceImportItem.objects.create(
            job=job,
            sort_index=0,
            filename="file-1.pdf",
            file_path="tmp/file-1.pdf",
            status=InvoiceImportItem.STATUS_IMPORTED,
        )

        _update_invoice_import_job_counts(job.id)

        job.refresh_from_db()
        self.assertEqual(job.total_files, 1)
        self.assertEqual(job.processed_files, 1)
        self.assertEqual(job.status, InvoiceImportJob.STATUS_COMPLETED)
        self.assertEqual(job.progress, 100)

    def test_import_job_progress_is_capped_at_100(self):
        job = InvoiceImportJob.objects.create(status=InvoiceImportJob.STATUS_PROCESSING, total_files=1)
        InvoiceImportItem.objects.create(
            job=job,
            sort_index=0,
            filename="file-1.pdf",
            file_path="tmp/file-1.pdf",
            status=InvoiceImportItem.STATUS_IMPORTED,
        )
        InvoiceImportItem.objects.create(
            job=job,
            sort_index=1,
            filename="file-2.pdf",
            file_path="tmp/file-2.pdf",
            status=InvoiceImportItem.STATUS_DUPLICATE,
        )

        _update_invoice_import_job_counts(job.id)

        job.refresh_from_db()
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.status, InvoiceImportJob.STATUS_COMPLETED)

    def test_import_job_is_failed_when_all_items_fail(self):
        job = InvoiceImportJob.objects.create(status=InvoiceImportJob.STATUS_PROCESSING, total_files=2)
        InvoiceImportItem.objects.create(
            job=job,
            sort_index=0,
            filename="file-1.pdf",
            file_path="tmp/file-1.pdf",
            status=InvoiceImportItem.STATUS_ERROR,
        )
        InvoiceImportItem.objects.create(
            job=job,
            sort_index=1,
            filename="file-2.pdf",
            file_path="tmp/file-2.pdf",
            status=InvoiceImportItem.STATUS_ERROR,
        )

        _update_invoice_import_job_counts(job.id)

        job.refresh_from_db()
        self.assertEqual(job.processed_files, 2)
        self.assertEqual(job.error_count, 2)
        self.assertEqual(job.status, InvoiceImportJob.STATUS_FAILED)
        self.assertEqual(job.progress, 100)

    def test_import_job_is_completed_when_not_all_items_fail(self):
        job = InvoiceImportJob.objects.create(status=InvoiceImportJob.STATUS_PROCESSING, total_files=2)
        InvoiceImportItem.objects.create(
            job=job,
            sort_index=0,
            filename="file-1.pdf",
            file_path="tmp/file-1.pdf",
            status=InvoiceImportItem.STATUS_IMPORTED,
        )
        InvoiceImportItem.objects.create(
            job=job,
            sort_index=1,
            filename="file-2.pdf",
            file_path="tmp/file-2.pdf",
            status=InvoiceImportItem.STATUS_ERROR,
        )

        _update_invoice_import_job_counts(job.id)

        job.refresh_from_db()
        self.assertEqual(job.processed_files, 2)
        self.assertEqual(job.imported_count, 1)
        self.assertEqual(job.error_count, 1)
        self.assertEqual(job.status, InvoiceImportJob.STATUS_COMPLETED)
        self.assertEqual(job.progress, 100)

    def test_import_job_counter_recompute_is_idempotent_across_multiple_calls(self):
        job = InvoiceImportJob.objects.create(status=InvoiceImportJob.STATUS_PROCESSING, total_files=2)
        InvoiceImportItem.objects.create(
            job=job,
            sort_index=0,
            filename="file-1.pdf",
            file_path="tmp/file-1.pdf",
            status=InvoiceImportItem.STATUS_IMPORTED,
        )
        InvoiceImportItem.objects.create(
            job=job,
            sort_index=1,
            filename="file-2.pdf",
            file_path="tmp/file-2.pdf",
            status=InvoiceImportItem.STATUS_DUPLICATE,
        )

        _update_invoice_import_job_counts(job.id)
        _update_invoice_import_job_counts(job.id)

        job.refresh_from_db()
        self.assertEqual(job.processed_files, 2)
        self.assertEqual(job.imported_count, 1)
        self.assertEqual(job.duplicate_count, 1)
        self.assertEqual(job.error_count, 0)
        self.assertEqual(job.status, InvoiceImportJob.STATUS_COMPLETED)


class InvoiceDocumentJobStatusAggregationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="doc-job-user", password="testpass")
        self.customer = Customer.objects.create(first_name="Doc", last_name="Job")
        self.invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=7),
            created_by=self.user,
        )
        self.second_invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=10),
            created_by=self.user,
        )

    def test_document_job_is_failed_when_all_items_fail(self):
        job = InvoiceDocumentJob.objects.create(
            status=InvoiceDocumentJob.STATUS_QUEUED,
            format_type=InvoiceDocumentJob.FORMAT_DOCX,
            total_invoices=1,
            created_by=self.user,
        )
        InvoiceDocumentItem.objects.create(
            job=job,
            sort_index=0,
            invoice=self.invoice,
            status=InvoiceDocumentItem.STATUS_QUEUED,
        )

        class FailingInvoiceService:
            def __init__(self, invoice):
                self.invoice = invoice

            def generate_invoice_data(self):
                raise RuntimeError("simulated generation failure")

            def generate_invoice_document(self, *args, **kwargs):
                return BytesIO(b"unused")

            def generate_partial_invoice_data(self):
                raise RuntimeError("simulated generation failure")

        with (
            patch("invoices.tasks.document_jobs.acquire_task_lock", return_value="token-doc"),
            patch("invoices.tasks.document_jobs.release_task_lock"),
            patch("invoices.tasks.document_jobs.InvoiceService", FailingInvoiceService),
            patch(
                "invoices.tasks.document_jobs.default_storage.save", return_value="tmpfiles/invoice_documents/test.zip"
            ) as save_mock,
        ):
            _run_huey_task(run_invoice_document_job, job_id=str(job.id))

        job.refresh_from_db()
        item = job.items.get()
        save_mock.assert_not_called()

        self.assertEqual(item.status, InvoiceDocumentItem.STATUS_FAILED)
        self.assertEqual(job.status, InvoiceDocumentJob.STATUS_FAILED)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.output_path, "")
        # result should have summary counters
        self.assertIsNotNone(job.result)
        self.assertEqual(job.result.get("completed_items"), 0)
        self.assertEqual(job.result.get("failed_items"), 1)
        self.assertIn("Failed to generate all requested invoice documents", job.error_message)

    def test_document_job_with_partial_failures_sets_warning_and_output(self):
        job = InvoiceDocumentJob.objects.create(
            status=InvoiceDocumentJob.STATUS_QUEUED,
            format_type=InvoiceDocumentJob.FORMAT_DOCX,
            total_invoices=2,
            created_by=self.user,
        )
        InvoiceDocumentItem.objects.create(
            job=job,
            sort_index=0,
            invoice=self.invoice,
            status=InvoiceDocumentItem.STATUS_QUEUED,
        )
        InvoiceDocumentItem.objects.create(
            job=job,
            sort_index=1,
            invoice=self.second_invoice,
            status=InvoiceDocumentItem.STATUS_QUEUED,
        )

        failing_invoice_id = self.invoice.id

        class MixedInvoiceService:
            def __init__(self, invoice):
                self.invoice = invoice

            def generate_invoice_data(self):
                if self.invoice.id == failing_invoice_id:
                    raise RuntimeError("simulated generation failure")
                return ({"invoice_no": self.invoice.invoice_no_display}, [])

            def generate_invoice_document(self, *args, **kwargs):
                return BytesIO(b"doc-content")

            def generate_partial_invoice_data(self):
                if self.invoice.id == failing_invoice_id:
                    raise RuntimeError("simulated generation failure")
                return ({"invoice_no": self.invoice.invoice_no_display}, [], [])

        with (
            patch("invoices.tasks.document_jobs.acquire_task_lock", return_value="token-doc-mixed"),
            patch("invoices.tasks.document_jobs.release_task_lock"),
            patch("invoices.tasks.document_jobs.InvoiceService", MixedInvoiceService),
            patch(
                "invoices.tasks.document_jobs.default_storage.save",
                return_value="tmpfiles/invoice_documents/mixed.zip",
            ) as save_mock,
        ):
            _run_huey_task(run_invoice_document_job, job_id=str(job.id))

        job.refresh_from_db()
        self.assertEqual(job.status, InvoiceDocumentJob.STATUS_COMPLETED)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.output_path, "tmpfiles/invoice_documents/mixed.zip")
        self.assertIn("Completed with 1 failed invoice document(s)", job.error_message)
        self.assertIsNotNone(job.result)
        self.assertEqual(job.result.get("completed_items"), 1)
        self.assertEqual(job.result.get("failed_items"), 1)
        save_mock.assert_called_once()

    def test_document_job_with_no_items_completes_without_output_zip(self):
        job = InvoiceDocumentJob.objects.create(
            status=InvoiceDocumentJob.STATUS_QUEUED,
            format_type=InvoiceDocumentJob.FORMAT_DOCX,
            total_invoices=3,
            processed_invoices=2,
            created_by=self.user,
        )

        with (
            patch("invoices.tasks.document_jobs.acquire_task_lock", return_value="token-doc-empty"),
            patch("invoices.tasks.document_jobs.release_task_lock"),
            patch("invoices.tasks.document_jobs.default_storage.save") as save_mock,
        ):
            _run_huey_task(run_invoice_document_job, job_id=str(job.id))

        job.refresh_from_db()
        save_mock.assert_not_called()
        self.assertEqual(job.status, InvoiceDocumentJob.STATUS_COMPLETED)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.total_invoices, 0)
        self.assertEqual(job.processed_invoices, 0)
        self.assertEqual(job.output_path, "")
        self.assertIsNotNone(job.result)
        self.assertEqual(job.result.get("total_items"), 0)

    def test_document_job_syncs_total_invoices_to_actual_item_count(self):
        job = InvoiceDocumentJob.objects.create(
            status=InvoiceDocumentJob.STATUS_QUEUED,
            format_type=InvoiceDocumentJob.FORMAT_DOCX,
            total_invoices=99,
            created_by=self.user,
        )
        InvoiceDocumentItem.objects.create(
            job=job,
            sort_index=0,
            invoice=self.invoice,
            status=InvoiceDocumentItem.STATUS_QUEUED,
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
            patch("invoices.tasks.document_jobs.acquire_task_lock", return_value="token-doc-sync-total"),
            patch("invoices.tasks.document_jobs.release_task_lock"),
            patch("invoices.tasks.document_jobs.InvoiceService", SuccessfulInvoiceService),
            patch(
                "invoices.tasks.document_jobs.default_storage.save", return_value="tmpfiles/invoice_documents/one.zip"
            ),
        ):
            _run_huey_task(run_invoice_document_job, job_id=str(job.id))

        job.refresh_from_db()
        self.assertEqual(job.total_invoices, 1)
        self.assertEqual(job.processed_invoices, 1)
        self.assertEqual(job.progress, 100)

    def test_document_item_success_clears_stale_error_fields(self):
        job = InvoiceDocumentJob.objects.create(
            status=InvoiceDocumentJob.STATUS_QUEUED,
            format_type=InvoiceDocumentJob.FORMAT_DOCX,
            total_invoices=1,
            created_by=self.user,
        )
        item = InvoiceDocumentItem.objects.create(
            job=job,
            sort_index=0,
            invoice=self.invoice,
            status=InvoiceDocumentItem.STATUS_QUEUED,
            error_message="old item error",
            traceback="old item traceback",
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
            patch("invoices.tasks.document_jobs.acquire_task_lock", return_value="token-doc-clean-item"),
            patch("invoices.tasks.document_jobs.release_task_lock"),
            patch("invoices.tasks.document_jobs.InvoiceService", SuccessfulInvoiceService),
            patch(
                "invoices.tasks.document_jobs.default_storage.save", return_value="tmpfiles/invoice_documents/ok.zip"
            ),
        ):
            _run_huey_task(run_invoice_document_job, job_id=str(job.id))

        item.refresh_from_db()
        self.assertEqual(item.status, InvoiceDocumentItem.STATUS_COMPLETED)
        self.assertEqual(item.error_message, "")
        self.assertEqual(item.traceback, "")


class InvoiceImportItemStateCleanupTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="import-item-cleanup-user", password="testpass")
        self.job = InvoiceImportJob.objects.create(
            status=InvoiceImportJob.STATUS_QUEUED,
            total_files=1,
            created_by=self.user,
        )

    def test_import_item_success_clears_stale_error_fields(self):
        item = InvoiceImportItem.objects.create(
            job=self.job,
            sort_index=0,
            filename="invoice.pdf",
            file_path="tmp/invoice.pdf",
            status=InvoiceImportItem.STATUS_QUEUED,
            error_message="old import error",
            traceback="old import traceback",
        )

        @contextmanager
        def fake_open(*args, **kwargs):
            yield BytesIO(b"fake-pdf-content")

        fake_result = SimpleNamespace(
            success=True,
            status="imported",
            message="Imported",
            invoice=None,
            customer=None,
            errors=[],
        )

        class FakeImporter:
            def __init__(self, *args, **kwargs):
                pass

            def import_from_file(self, file_bytes, file_name):
                return fake_result

        with (
            patch("invoices.tasks.import_jobs.acquire_task_lock", return_value="token-import-clean-item"),
            patch("invoices.tasks.import_jobs.release_task_lock"),
            patch("invoices.tasks.import_jobs.default_storage.open", fake_open),
            patch("invoices.tasks.import_jobs.InvoiceImporter", FakeImporter),
        ):
            _run_huey_task(run_invoice_import_item, item_id=str(item.id))

        item.refresh_from_db()
        self.assertEqual(item.status, InvoiceImportItem.STATUS_IMPORTED)
        self.assertEqual(item.error_message, "")
        self.assertEqual(item.traceback, "")
