from datetime import date, timedelta
from unittest.mock import patch

from core.tasks.document_validation import run_document_validation
from customer_applications.models import DocApplication, Document
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from products.models import Product
from products.models.document_type import DocumentType


def _run_task(task, **kwargs):
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
            has_doc_number=True,
            has_details=True,
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
            "extracted_doc_number": "ITK-2030-7788",
            "extracted_details_markdown": "## ITK\n- Permit Number: ITK-2030-7788",
        }

        _run_task(run_document_validation, document_id=self.document.id)

        self.document.refresh_from_db()
        self.assertEqual(self.document.ai_validation_status, Document.AI_VALIDATION_VALID)
        self.assertEqual(self.document.expiration_date, date(2030, 1, 9))
        self.assertEqual(self.document.doc_number, "ITK-2030-7788")
        self.assertEqual(self.document.details, "## ITK\n- Permit Number: ITK-2030-7788")
        self.assertEqual(self.document.ai_validation_result.get("extracted_expiration_date"), "2030-01-09")
        self.assertEqual(self.document.ai_validation_result.get("extracted_doc_number"), "ITK-2030-7788")
        self.assertEqual(
            self.document.ai_validation_result.get("extracted_details_markdown"),
            "## ITK\n- Permit Number: ITK-2030-7788",
        )
        self.assertTrue(validate_document_mock.call_args.kwargs["require_expiration_date"])
        self.assertTrue(validate_document_mock.call_args.kwargs["require_doc_number"])
        self.assertTrue(validate_document_mock.call_args.kwargs["require_details"])
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
        self.document.doc_number = "EXISTING-DOC-NO"
        self.document.details = "Existing details"
        self.document.save()

        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"fake-file-bytes"
        validate_document_mock.return_value = {
            "valid": True,
            "confidence": 0.91,
            "positive_analysis": "Looks valid.",
            "negative_issues": [],
            "reasoning": "Checks passed.",
            "extracted_expiration_date": "2031-12-31",
            "extracted_doc_number": "NEW-DOC-NO",
            "extracted_details_markdown": "## New Details",
        }

        _run_task(run_document_validation, document_id=self.document.id)

        self.document.refresh_from_db()
        self.assertEqual(self.document.expiration_date, date(2029, 6, 1))
        self.assertEqual(self.document.doc_number, "EXISTING-DOC-NO")
        self.assertEqual(self.document.details, "Existing details")

    @patch("core.tasks.document_validation.default_storage.open")
    @patch("core.tasks.document_validation.AIDocumentCategorizer.validate_document")
    @patch("core.tasks.document_validation.acquire_task_lock", return_value="token-3")
    @patch("core.tasks.document_validation.release_task_lock")
    def test_validation_marks_expired_document_as_invalid(
        self,
        _release_lock_mock,
        _acquire_lock_mock,
        validate_document_mock,
        storage_open_mock,
    ):
        self.document.expiration_date = timezone.localdate() - timedelta(days=1)
        self.document.save(update_fields=["expiration_date", "updated_at"])

        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"fake-file-bytes"
        validate_document_mock.return_value = {
            "valid": True,
            "confidence": 0.95,
            "positive_analysis": "Looks valid.",
            "negative_issues": [],
            "reasoning": "Checks passed.",
            "extracted_expiration_date": None,
            "extracted_doc_number": None,
            "extracted_details_markdown": None,
        }

        _run_task(run_document_validation, document_id=self.document.id)

        self.document.refresh_from_db()
        self.assertEqual(self.document.ai_validation_status, Document.AI_VALIDATION_INVALID)
        self.assertEqual(self.document.ai_validation_result.get("expiration_state"), "expired")
        self.assertIn("expired on", self.document.ai_validation_result.get("expiration_reason", "").lower())
        self.assertFalse(self.document.ai_validation_result.get("valid"))

    @patch("core.tasks.document_validation.default_storage.open")
    @patch("core.tasks.document_validation.AIDocumentCategorizer.validate_document")
    @patch("core.tasks.document_validation.acquire_task_lock", return_value="token-4")
    @patch("core.tasks.document_validation.release_task_lock")
    def test_validation_marks_expiring_document_as_invalid(
        self,
        _release_lock_mock,
        _acquire_lock_mock,
        validate_document_mock,
        storage_open_mock,
    ):
        self.doc_type.expiring_threshold_days = 10
        self.doc_type.save(update_fields=["expiring_threshold_days"])
        self.document.expiration_date = timezone.localdate() + timedelta(days=3)
        self.document.save(update_fields=["expiration_date", "updated_at"])

        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"fake-file-bytes"
        validate_document_mock.return_value = {
            "valid": True,
            "confidence": 0.93,
            "positive_analysis": "Looks valid.",
            "negative_issues": [],
            "reasoning": "Checks passed.",
            "extracted_expiration_date": None,
            "extracted_doc_number": None,
            "extracted_details_markdown": None,
        }

        _run_task(run_document_validation, document_id=self.document.id)

        self.document.refresh_from_db()
        self.assertEqual(self.document.ai_validation_status, Document.AI_VALIDATION_INVALID)
        self.assertEqual(self.document.ai_validation_result.get("expiration_state"), "expiring")
        self.assertIn("within 10 days", self.document.ai_validation_result.get("expiration_reason", ""))
        self.assertFalse(self.document.ai_validation_result.get("valid"))

    @patch("core.tasks.document_validation.default_storage.open")
    @patch("core.tasks.document_validation.AIDocumentCategorizer.validate_document")
    @patch("core.tasks.document_validation.acquire_task_lock", return_value="token-5")
    @patch("core.tasks.document_validation.release_task_lock")
    def test_validation_keeps_valid_when_not_expiring(
        self,
        _release_lock_mock,
        _acquire_lock_mock,
        validate_document_mock,
        storage_open_mock,
    ):
        self.doc_type.expiring_threshold_days = 10
        self.doc_type.save(update_fields=["expiring_threshold_days"])
        self.document.expiration_date = timezone.localdate() + timedelta(days=40)
        self.document.save(update_fields=["expiration_date", "updated_at"])

        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"fake-file-bytes"
        validate_document_mock.return_value = {
            "valid": True,
            "confidence": 0.99,
            "positive_analysis": "Looks valid.",
            "negative_issues": [],
            "reasoning": "Checks passed.",
            "extracted_expiration_date": None,
            "extracted_doc_number": None,
            "extracted_details_markdown": None,
        }

        _run_task(run_document_validation, document_id=self.document.id)

        self.document.refresh_from_db()
        self.assertEqual(self.document.ai_validation_status, Document.AI_VALIDATION_VALID)
        self.assertEqual(self.document.ai_validation_result.get("expiration_state"), "ok")
        self.assertIsNone(self.document.ai_validation_result.get("expiration_reason"))
        self.assertTrue(self.document.ai_validation_result.get("valid"))
