from datetime import date
from unittest.mock import patch

from api.serializers.doc_application_serializer import DocApplicationCreateUpdateSerializer
from customer_applications.models import DocApplication, Document
from customer_applications.tasks import auto_import_passport_task
from customers.models import Customer
from django.core.files.base import ContentFile
from django.test import TestCase
from products.models import Product
from products.models.document_type import DocumentType
from rest_framework.test import APIRequestFactory


class DocApplicationCreatePerformanceTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user("perf-user", "perf@example.com", "pass")
        self.customer = Customer.objects.create(
            first_name="Perf",
            last_name="Customer",
            passport_number="P1234567",
            passport_issue_date=date(2020, 1, 1),
            passport_expiration_date=date(2030, 1, 1),
        )
        self.product = Product.objects.create(
            name="Perf Product",
            code="PERF-01",
            required_documents="Passport",
        )
        self.passport_doc_type = DocumentType.objects.create(name="Passport")
        self.factory = APIRequestFactory()

    def test_serializer_queues_passport_auto_import_after_commit(self):
        request = self.factory.post("/")
        request.user = self.user

        with (
            patch.object(DocApplicationCreateUpdateSerializer, "_can_auto_import_passport", return_value=True),
            patch("django.db.transaction.on_commit", side_effect=lambda callback: callback()),
            patch("customer_applications.tasks.auto_import_passport_task") as auto_import_mock,
        ):
            serializer = DocApplicationCreateUpdateSerializer(
                data={
                    "customer": self.customer.id,
                    "product": self.product.id,
                    "doc_date": "2026-03-06",
                    "document_types": [],
                },
                context={"request": request},
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            serializer.save()

        auto_import_mock.assert_called_once()
        self.assertEqual(Document.objects.count(), 0)

    def test_auto_import_task_recomputes_application_status_once(self):
        self.customer.passport_file.save("passport.pdf", ContentFile(b"passport-bytes"), save=True)

        application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 3, 6),
            created_by=self.user,
        )

        original_get_status = DocApplication._get_application_status

        with (
            patch.object(DocApplication, "_get_application_status", autospec=True, wraps=original_get_status) as status_mock,
            patch("customer_applications.services.thumbnail_service.DocumentThumbnailService.sync_for_document"),
        ):
            result = auto_import_passport_task.call_local(
                application_id=application.id,
                user_id=self.user.id,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source"], "customer_profile")
        self.assertEqual(status_mock.call_count, 1)
        self.assertEqual(
            Document.objects.filter(doc_application=application, doc_type=self.passport_doc_type).count(),
            1,
        )
