from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from invoices.models import InvoiceDocumentJob, InvoiceDownloadJob, InvoiceImportItem
from invoices.tasks.document_jobs import run_invoice_document_job
from invoices.tasks.download_jobs import run_invoice_download_job
from invoices.tasks.import_jobs import run_invoice_import_item


def _run_huey_task(task, **kwargs):
    if hasattr(task, "call_local"):
        return task.call_local(**kwargs)
    if hasattr(task, "func"):
        return task.func(**kwargs)
    return task(**kwargs)


class InvoiceTaskRuntimeIdempotencyTests(SimpleTestCase):
    def test_run_invoice_download_job_skips_when_lock_is_contended(self):
        with (
            patch("invoices.tasks.download_jobs.acquire_task_lock", return_value=None),
            patch("invoices.tasks.download_jobs.InvoiceDownloadJob.objects.select_related") as select_related_mock,
        ):
            _run_huey_task(run_invoice_download_job, job_id="job-300")

        select_related_mock.assert_not_called()

    def test_run_invoice_download_job_releases_lock_when_job_missing(self):
        with (
            patch("invoices.tasks.download_jobs.acquire_task_lock", return_value="token-1"),
            patch("invoices.tasks.download_jobs.release_task_lock") as release_lock_mock,
            patch(
                "invoices.tasks.download_jobs.InvoiceDownloadJob.objects.select_related",
                side_effect=InvoiceDownloadJob.DoesNotExist,
            ),
        ):
            _run_huey_task(run_invoice_download_job, job_id="job-300")

        release_lock_mock.assert_called_once_with("tasks:idempotency:invoice_download_job:job-300", "token-1")

    def test_run_invoice_import_item_skips_when_lock_is_contended(self):
        with (
            patch("invoices.tasks.import_jobs.acquire_task_lock", return_value=None),
            patch("invoices.tasks.import_jobs.InvoiceImportItem.objects.select_related") as select_related_mock,
        ):
            _run_huey_task(run_invoice_import_item, item_id="item-400")

        select_related_mock.assert_not_called()

    def test_run_invoice_import_item_releases_lock_when_item_missing(self):
        with (
            patch("invoices.tasks.import_jobs.acquire_task_lock", return_value="token-2"),
            patch("invoices.tasks.import_jobs.release_task_lock") as release_lock_mock,
            patch(
                "invoices.tasks.import_jobs.InvoiceImportItem.objects.select_related",
                side_effect=InvoiceImportItem.DoesNotExist,
            ),
        ):
            _run_huey_task(run_invoice_import_item, item_id="item-400")

        release_lock_mock.assert_called_once_with("tasks:idempotency:invoice_import_item:item-400", "token-2")

    def test_run_invoice_import_item_skips_when_item_already_terminal(self):
        item = SimpleNamespace(
            status=InvoiceImportItem.STATUS_IMPORTED,
            job_id="job-import-1",
            job=SimpleNamespace(status="processing"),
            save=lambda *args, **kwargs: None,
        )

        with (
            patch("invoices.tasks.import_jobs.acquire_task_lock", return_value="token-2a"),
            patch("invoices.tasks.import_jobs.release_task_lock") as release_lock_mock,
            patch("invoices.tasks.import_jobs._update_invoice_import_job_counts") as update_counts_mock,
            patch("invoices.tasks.import_jobs.InvoiceImportItem.objects.select_related") as select_related_mock,
        ):
            select_related_mock.return_value.get.return_value = item
            _run_huey_task(run_invoice_import_item, item_id="item-401")

        update_counts_mock.assert_called_once_with("job-import-1")
        release_lock_mock.assert_called_once_with("tasks:idempotency:invoice_import_item:item-401", "token-2a")

    def test_run_invoice_download_job_skips_when_job_already_finalized(self):
        job = SimpleNamespace(
            status=InvoiceDownloadJob.STATUS_COMPLETED,
            save=lambda *args, **kwargs: None,
        )

        with (
            patch("invoices.tasks.download_jobs.acquire_task_lock", return_value="token-1a"),
            patch("invoices.tasks.download_jobs.release_task_lock") as release_lock_mock,
            patch("invoices.tasks.download_jobs.InvoiceDownloadJob.objects.select_related") as select_related_mock,
        ):
            select_related_mock.return_value.get.return_value = job
            _run_huey_task(run_invoice_download_job, job_id="job-301")

        release_lock_mock.assert_called_once_with("tasks:idempotency:invoice_download_job:job-301", "token-1a")

    def test_run_invoice_document_job_skips_when_lock_is_contended(self):
        with (
            patch("invoices.tasks.document_jobs.acquire_task_lock", return_value=None),
            patch("invoices.tasks.document_jobs.InvoiceDocumentJob.objects.get") as get_job_mock,
        ):
            _run_huey_task(run_invoice_document_job, job_id="job-500")

        get_job_mock.assert_not_called()

    def test_run_invoice_document_job_releases_lock_when_job_missing(self):
        with (
            patch("invoices.tasks.document_jobs.acquire_task_lock", return_value="token-3"),
            patch("invoices.tasks.document_jobs.release_task_lock") as release_lock_mock,
            patch(
                "invoices.tasks.document_jobs.InvoiceDocumentJob.objects.get",
                side_effect=InvoiceDocumentJob.DoesNotExist,
            ),
        ):
            _run_huey_task(run_invoice_document_job, job_id="job-500")

        release_lock_mock.assert_called_once_with("tasks:idempotency:invoice_document_job:job-500", "token-3")

    def test_run_invoice_document_job_skips_when_job_already_finalized(self):
        job = SimpleNamespace(
            status=InvoiceDocumentJob.STATUS_COMPLETED,
            save=lambda *args, **kwargs: None,
        )

        with (
            patch("invoices.tasks.document_jobs.acquire_task_lock", return_value="token-3a"),
            patch("invoices.tasks.document_jobs.release_task_lock") as release_lock_mock,
            patch("invoices.tasks.document_jobs.InvoiceDocumentJob.objects.get", return_value=job),
        ):
            _run_huey_task(run_invoice_document_job, job_id="job-501")

        release_lock_mock.assert_called_once_with("tasks:idempotency:invoice_document_job:job-501", "token-3a")
