from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.models import AsyncJob
from django.core.files.storage import FileSystemStorage
from django.test import TestCase
from products.models import Product, ProductCategory
from products.tasks.price_list_jobs import run_product_price_list_print_job


def _run_huey_task(task, **kwargs):
    if hasattr(task, "call_local"):
        return task.call_local(**kwargs)
    if hasattr(task, "func"):
        return task.func(**kwargs)
    return task(**kwargs)


class ProductPriceListJobTests(TestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = TemporaryDirectory()
        self.storage = FileSystemStorage(location=self.temp_dir.name, base_url="/media/")

    def tearDown(self):
        self.temp_dir.cleanup()
        super().tearDown()

    def test_job_generates_and_stores_pdf(self):
        category = ProductCategory.objects.create(name="Single Entry Visa", product_type="visa")
        Product.objects.create(
            product_category=category,
            code="PDF-1",
            name="Printable Product",
            base_price=Decimal("100000.00"),
            retail_price=Decimal("250000.00"),
            currency="IDR",
        )
        job = AsyncJob.objects.create(task_name="products_price_list_print", status=AsyncJob.STATUS_PENDING)

        with (
            patch("products.tasks.price_list_jobs.default_storage", self.storage),
            patch("products.tasks.price_list_jobs.acquire_task_lock", return_value="token-print"),
            patch("products.tasks.price_list_jobs.release_task_lock"),
            patch("products.tasks.price_list_jobs.PDFConverter.docx_buffer_to_pdf", return_value=b"%PDF-1.7 test"),
        ):
            _run_huey_task(run_product_price_list_print_job, job_id=str(job.id))

        job.refresh_from_db()
        self.assertEqual(job.status, AsyncJob.STATUS_COMPLETED)
        self.assertIsNotNone(job.result)
        result = job.result or {}
        self.assertEqual(result["content_type"], "application/pdf")
        self.assertEqual(result["total_products"], 1)
        self.assertEqual(result["total_categories"], 1)
        self.assertTrue(self.storage.exists(result["file_path"]))

        with self.storage.open(result["file_path"], "rb") as stored:
            self.assertEqual(stored.read(), b"%PDF-1.7 test")
