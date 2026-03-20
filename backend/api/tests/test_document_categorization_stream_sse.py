from unittest.mock import patch

from customer_applications.models import DocApplication, Document, DocumentCategorizationJob
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from products.models import DocumentType, Product
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


User = get_user_model()


class DocumentCategorizationStreamSseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="categorization-stream-user",
            email="categorization-stream-user@example.com",
            password="pass",
        )
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")

        self.customer = Customer.objects.create(customer_type="person", first_name="Stream", last_name="Owner")
        self.product = Product.objects.create(name="Stream Product", code="STREAM-PROD", product_type="visa")
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

    @staticmethod
    def _decode_chunk(chunk) -> str:
        if isinstance(chunk, bytes):
            return chunk.decode("utf-8")
        return chunk

    @patch("api.views_categorization.iter_replay_and_live_events")
    def test_categorization_stream_returns_start_and_keepalive(self, iter_events_mock):
        iter_events_mock.return_value = iter([None])
        job = DocumentCategorizationJob.objects.create(
            doc_application=self.application,
            created_by=self.user,
            total_files=1,
            result={
                "stage": "uploading",
                "upload": {
                    "total_files": 1,
                    "uploaded_files": 0,
                    "uploaded_bytes": 0,
                    "total_bytes": 0,
                    "complete": False,
                },
                "overall_progress_percent": 0,
            },
        )

        response = self.client.get(reverse("api-categorization-stream-sse", kwargs={"job_id": str(job.id)}))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/event-stream"))

        stream = iter(response.streaming_content)
        first_chunk = self._decode_chunk(next(stream))
        second_chunk = self._decode_chunk(next(stream))
        third_chunk = self._decode_chunk(next(stream))

        self.assertIn("event: start", first_chunk)
        self.assertIn(f'"jobId": "{job.id}"', first_chunk)
        self.assertIn("event: progress", second_chunk)
        self.assertIn(f'"jobId": "{job.id}"', second_chunk)
        self.assertIn("event: upload_progress", third_chunk)
        self.assertIn(f'"jobId": "{job.id}"', third_chunk)

    @patch("api.views_categorization.iter_replay_and_live_events")
    def test_document_validation_stream_returns_start_and_keepalive(self, iter_events_mock):
        iter_events_mock.return_value = iter([None])
        doc_type = DocumentType.objects.create(name="Passport")
        document = Document.objects.create(
            doc_application=self.application,
            doc_type=doc_type,
            created_by=self.user,
        )

        response = self.client.get(
            reverse("api-document-validation-stream", kwargs={"document_id": document.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/event-stream"))

        stream = iter(response.streaming_content)
        first_chunk = self._decode_chunk(next(stream))
        second_chunk = self._decode_chunk(next(stream))

        self.assertIn("event: start", first_chunk)
        self.assertIn(f'"documentId": {document.id}', first_chunk)
        self.assertEqual(second_chunk, ": keep-alive\n\n")
        iter_events_mock.assert_called_once()
