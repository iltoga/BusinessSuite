from unittest.mock import patch

from customer_applications.models import DocApplication, DocumentCategorizationItem, DocumentCategorizationJob
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from products.models import Product


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class DocumentCategorizationUploadProgressTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="categorizer_progress",
            email="categorizer.progress@example.com",
            password="password",
        )
        self.client.force_login(self.user)

        self.customer = Customer.objects.create(customer_type="person", first_name="Bulk", last_name="Upload")
        self.product = Product.objects.create(name="Bulk Product", code="BULK-UPLOAD", product_type="visa")
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

    def test_init_creates_job_with_upload_stage_payload(self):
        url = reverse("api-categorize-documents-init", kwargs={"application_id": self.application.id})
        response = self.client.post(url, data={"totalFiles": 2})

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["totalFiles"], 2)

        job = DocumentCategorizationJob.objects.get(id=body["jobId"])
        self.assertEqual(job.total_files, 2)
        # result should be initialized by the view
        self.assertIsNotNone(job.result)
        self.assertIsInstance(job.result, dict)
        self.assertEqual(job.result.get("stage"), "uploading")
        self.assertEqual(job.result.get("upload", {}).get("uploaded_files"), 0)
        self.assertEqual(job.result.get("upload", {}).get("total_files"), 2)
        self.assertEqual(job.result.get("overall_progress_percent"), 0)
        self.assertFalse(job.result.get("upload", {}).get("complete"))

    @patch("api.views_categorization.run_document_categorization_item")
    @patch("api.views_categorization.default_storage.save", side_effect=lambda path, _content: path)
    def test_upload_updates_progress_and_dispatches_items(self, _storage_save_mock, run_task_mock):
        init_url = reverse("api-categorize-documents-init", kwargs={"application_id": self.application.id})
        init_response = self.client.post(init_url, data={"totalFiles": 2})
        self.assertEqual(init_response.status_code, 201, init_response.content)
        job_id = init_response.json()["jobId"]

        upload_url = reverse("api-categorization-upload-files", kwargs={"job_id": job_id})
        file_1 = SimpleUploadedFile("flight_ticket.pdf", b"flight-pdf-bytes", content_type="application/pdf")
        file_2 = SimpleUploadedFile("itk.pdf", b"itk-pdf-bytes", content_type="application/pdf")

        response = self.client.post(upload_url, data={"files": [file_1, file_2]})

        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertEqual(body["uploadedFiles"], 2)
        self.assertEqual(body["dispatchedTasks"], 2)

        job = DocumentCategorizationJob.objects.get(id=job_id)
        self.assertIsNotNone(job.result)
        self.assertIsInstance(job.result, dict)
        self.assertEqual(job.result.get("stage"), "uploaded")
        self.assertTrue(job.result.get("upload", {}).get("complete"))
        self.assertEqual(job.result.get("upload", {}).get("uploaded_files"), 2)
        self.assertEqual(job.result.get("upload", {}).get("total_files"), 2)
        self.assertEqual(job.result.get("overall_progress_percent"), 40)

        self.assertEqual(DocumentCategorizationItem.objects.filter(job=job).count(), 2)
        self.assertEqual(run_task_mock.call_count, 2)
