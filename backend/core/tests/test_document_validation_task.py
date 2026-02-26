from datetime import date
from unittest.mock import patch

from core.tasks.document_validation import run_document_validation
from customer_applications.models import DocApplication, Document
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from products.models import Product
from products.models.document_type import DocumentType


def _run_huey_task(task, **kwargs):
    if hasattr(task, "call_local"):
        return task.call_local(**kwargs)
    if hasattr(task, "func"):
        return task.func(**kwargs)
    return task(**kwargs)


class DocumentValidationTaskTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="validator", password="pw")
        self.customer = Customer.objects.create(customer_type="person", first_name="Test", last_name="Customer")
        self.product = Product.objects.create(name="Visa Product", code="VISA-VAL", product_type="visa")
        self.doc_type = DocumentType.objects.create(
            name="ITK Validation",
            ai_validation=True,
            has_expiration_date=True,
            validation_rule_ai_positive="Document must be a valid ITK permit.",
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
            file="tmp/itk-validation.pdf",
            created_by=self.user,
        )

    @patch("core.tasks.document_validation.default_storage.open")
    @patch("core.tasks.document_validation.AIDocumentCategorizer.validate_document")
    @patch("core.tasks.document_validation.acquire_task_lock", return_value="token-1")
    @patch("core.tasks.document_validation.release_task_lock")
    def test_validation_sets_expiration_date_from_ai_output(
        self,
        release_lock_mock,
        _acquire_lock_mock,
        validate_document_mock,
        storage_open_mock,
    ):
        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"fake-file-bytes"
        validate_document_mock.return_value = {
            "valid": True,
            "confidence": 0.98,
            "positive_analysis": "Looks valid.",
            "negative_issues": [],
            "reasoning": "Checks passed.",
            "extracted_expiration_date": "2030-01-09",
        }

        _run_huey_task(run_document_validation, document_id=self.document.id)

        self.document.refresh_from_db()
        self.assertEqual(self.document.ai_validation_status, Document.AI_VALIDATION_VALID)
        self.assertEqual(self.document.expiration_date, date(2030, 1, 9))
        self.assertEqual(self.document.ai_validation_result.get("extracted_expiration_date"), "2030-01-09")
        self.assertTrue(validate_document_mock.call_args.kwargs["require_expiration_date"])
        release_lock_mock.assert_called_once()

    @patch("core.tasks.document_validation.default_storage.open")
    @patch("core.tasks.document_validation.AIDocumentCategorizer.validate_document")
    @patch("core.tasks.document_validation.acquire_task_lock", return_value="token-2")
    @patch("core.tasks.document_validation.release_task_lock")
    def test_validation_does_not_override_existing_expiration_date(
        self,
        _release_lock_mock,
        _acquire_lock_mock,
        validate_document_mock,
        storage_open_mock,
    ):
        self.document.expiration_date = date(2029, 6, 1)
        self.document.save()

        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"fake-file-bytes"
        validate_document_mock.return_value = {
            "valid": True,
            "confidence": 0.91,
            "positive_analysis": "Looks valid.",
            "negative_issues": [],
            "reasoning": "Checks passed.",
            "extracted_expiration_date": "2031-12-31",
        }

        _run_huey_task(run_document_validation, document_id=self.document.id)

        self.document.refresh_from_db()
        self.assertEqual(self.document.expiration_date, date(2029, 6, 1))
