from unittest.mock import patch

from django.test import SimpleTestCase

from core.models import AsyncJob
from products.tasks.product_excel_jobs import run_product_export_job, run_product_import_job


def _run_huey_task(task, **kwargs):
    if hasattr(task, "call_local"):
        return task.call_local(**kwargs)
    if hasattr(task, "func"):
        return task.func(**kwargs)
    return task(**kwargs)


class ProductTaskRuntimeIdempotencyTests(SimpleTestCase):
    def test_run_product_export_job_skips_when_lock_is_contended(self):
        with (
            patch("products.tasks.product_excel_jobs.acquire_task_lock", return_value=None),
            patch("products.tasks.product_excel_jobs.AsyncJob.objects.get") as get_job_mock,
        ):
            _run_huey_task(run_product_export_job, job_id="job-100")

        get_job_mock.assert_not_called()

    def test_run_product_export_job_releases_lock_when_job_missing(self):
        with (
            patch("products.tasks.product_excel_jobs.acquire_task_lock", return_value="token-1"),
            patch("products.tasks.product_excel_jobs.release_task_lock") as release_lock_mock,
            patch("products.tasks.product_excel_jobs.AsyncJob.objects.get", side_effect=AsyncJob.DoesNotExist),
        ):
            _run_huey_task(run_product_export_job, job_id="job-100")

        release_lock_mock.assert_called_once_with("tasks:idempotency:products_export_job:job-100", "token-1")

    def test_run_product_import_job_skips_when_lock_is_contended(self):
        with (
            patch("products.tasks.product_excel_jobs.acquire_task_lock", return_value=None),
            patch("products.tasks.product_excel_jobs.AsyncJob.objects.get") as get_job_mock,
        ):
            _run_huey_task(run_product_import_job, job_id="job-200", file_path="tmpfiles/in.xlsx")

        get_job_mock.assert_not_called()

    def test_run_product_import_job_releases_lock_when_job_missing(self):
        with (
            patch("products.tasks.product_excel_jobs.acquire_task_lock", return_value="token-2"),
            patch("products.tasks.product_excel_jobs.release_task_lock") as release_lock_mock,
            patch("products.tasks.product_excel_jobs.AsyncJob.objects.get", side_effect=AsyncJob.DoesNotExist),
        ):
            _run_huey_task(run_product_import_job, job_id="job-200", file_path="tmpfiles/in.xlsx")

        release_lock_mock.assert_called_once_with("tasks:idempotency:products_import_job:job-200", "token-2")
