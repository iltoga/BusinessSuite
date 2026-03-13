from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.models import AsyncJob
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import TestCase


class ProductPriceListApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user("price-list-user", "price@example.com", "pass")
        self.client.force_login(self.user)

    @patch("products.tasks.run_product_price_list_print_job")
    def test_start_endpoint_creates_async_job(self, enqueue_mock):
        response = self.client.post("/api/products/price-list/print/start/", {}, content_type="application/json")

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertTrue(payload["queued"])
        self.assertFalse(payload["deduplicated"])
        self.assertEqual(
            AsyncJob.objects.filter(task_name="products_price_list_print", created_by=self.user).count(), 1
        )
        enqueue_mock.assert_called_once()

    def test_download_endpoint_streams_generated_pdf(self):
        with TemporaryDirectory() as temp_dir:
            storage = FileSystemStorage(location=temp_dir, base_url="/media/")
            saved_path = storage.save("tmpfiles/product_price_lists/test.pdf", ContentFile(b"%PDF-1.7 test"))
            job = AsyncJob.objects.create(
                task_name="products_price_list_print",
                status=AsyncJob.STATUS_COMPLETED,
                created_by=self.user,
                result={
                    "file_path": saved_path,
                    "filename": "public_price_list.pdf",
                    "content_type": "application/pdf",
                },
            )

            with patch("api.views.default_storage", storage):
                response = self.client.get(f"/api/products/price-list/print/download/{job.id}/")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertIn('inline; filename="public_price_list.pdf"', response["Content-Disposition"])
            self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.7 test")
