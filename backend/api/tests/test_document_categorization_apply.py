import json
from datetime import date
from unittest.mock import patch

from customer_applications.models import (
    DocApplication,
    Document,
    DocumentCategorizationItem,
    DocumentCategorizationJob,
)
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from products.models import Product
from products.models.document_type import DocumentType


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class DocumentCategorizationApplyTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="categorizer",
            email="categorizer@example.com",
            password="password",
        )
        self.client.force_login(self.user)

        self.customer = Customer.objects.create(customer_type="person", first_name="Bulk", last_name="Upload")
        self.product = Product.objects.create(name="Bulk Product", code="BULK-VAL", product_type="visa")
        self.doc_type = DocumentType.objects.create(
            name="ITK Bulk",
            ai_validation=True,
            has_expiration_date=True,
        )
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )
        self.document = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type,
            created_by=self.user,
        )
        self.job = DocumentCategorizationJob.objects.create(
            doc_application=self.application,
            total_files=1,
            created_by=self.user,
        )
        self.item = DocumentCategorizationItem.objects.create(
            job=self.job,
            filename="itk.pdf",
            file_path="tmp/categorization/test/itk.pdf",
            status=DocumentCategorizationItem.STATUS_CATEGORIZED,
            document_type=self.doc_type,
            document=self.document,
            validation_status="valid",
            validation_result={
                "valid": True,
                "confidence": 0.97,
                "positive_analysis": "Looks valid.",
                "negative_issues": [],
                "reasoning": "Checks passed.",
                "extracted_expiration_date": "2031-02-14",
            },
        )

    @patch("api.views_categorization.default_storage.delete")
    @patch("api.views_categorization.default_storage.exists", return_value=True)
    @patch("api.views_categorization.default_storage.save", side_effect=lambda path, _content: path)
    @patch("api.views_categorization.default_storage.open")
    def test_apply_persists_extracted_expiration_date(
        self,
        storage_open_mock,
        _storage_save_mock,
        _storage_exists_mock,
        _storage_delete_mock,
    ):
        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"file-bytes"

        url = reverse("api-categorization-apply", kwargs={"job_id": str(self.job.id)})
        payload = {
            "mappings": [
                {
                    "item_id": str(self.item.id),
                    "document_id": self.document.id,
                }
            ]
        }

        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["totalApplied"], 1)
        self.assertEqual(body["totalErrors"], 0)

        self.document.refresh_from_db()
        self.assertEqual(self.document.expiration_date, date(2031, 2, 14))
