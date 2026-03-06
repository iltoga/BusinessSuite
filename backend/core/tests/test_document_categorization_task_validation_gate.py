from unittest.mock import patch

import dramatiq
from core.services.ai_client import AIConnectionError
from core.tasks.document_categorization import _run_validation_step, run_document_categorization_item
from customer_applications.models import DocApplication, Document, DocumentCategorizationItem, DocumentCategorizationJob
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


class DocumentCategorizationValidationGateTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._publish_stream_event_patcher = patch("core.signals_streams.publish_stream_event", return_value=None)
        cls._publish_stream_event_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._publish_stream_event_patcher.stop()
        super().tearDownClass()

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="cat-gate-user", password="testpass")
        self.customer = Customer.objects.create(customer_type="person", first_name="Cat", last_name="Gate")
        self.product = Product.objects.create(name="Categorization Product", code="CAT-GATE", product_type="visa")
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )
        self.doc_type = DocumentType.objects.create(
            name="Passport Gate Test",
            ai_validation=True,
            has_file=True,
            validation_rule_ai_positive="Must be a valid passport document",
        )
        self.job = DocumentCategorizationJob.objects.create(
            doc_application=self.application,
            total_files=1,
            created_by=self.user,
        )
        self.item = DocumentCategorizationItem.objects.create(
            job=self.job,
            sort_index=0,
            filename="passport.pdf",
            file_path="tmp/categorization/passport.pdf",
            status=DocumentCategorizationItem.STATUS_QUEUED,
            result={"stage": "uploaded"},
        )

    @patch("core.tasks.document_categorization.acquire_task_lock", return_value="lock-token")
    @patch("core.tasks.document_categorization.release_task_lock")
    @patch("core.tasks.document_categorization.default_storage.open")
    @patch("core.tasks.document_categorization.get_document_types_for_prompt")
    @patch("core.tasks.document_categorization.AIDocumentCategorizer.categorize_file_two_pass")
    @patch("core.tasks.document_categorization._run_validation_step")
    def test_no_slot_skips_validation_even_when_doc_type_ai_validation_enabled(
        self,
        run_validation_step_mock,
        categorize_file_mock,
        get_types_mock,
        storage_open_mock,
        _release_lock_mock,
        _acquire_lock_mock,
    ):
        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"fake-file-bytes"
        get_types_mock.return_value = [{"id": self.doc_type.id, "name": self.doc_type.name}]
        categorize_file_mock.return_value = {
            "document_type_id": self.doc_type.id,
            "document_type": self.doc_type.name,
            "confidence": 0.95,
            "reasoning": "Looks like a passport.",
            "pass_used": 1,
        }

        _run_huey_task(run_document_categorization_item, item_id=str(self.item.id))

        self.item.refresh_from_db()
        self.assertEqual(self.item.status, DocumentCategorizationItem.STATUS_CATEGORIZED)
        self.assertIsNone(self.item.document_id)
        self.assertEqual(self.item.validation_status, "")
        self.assertEqual(self.item.result.get("ai_validation_enabled"), False)
        self.assertEqual(self.item.result.get("validation_skipped_reason"), "no_slot")
        run_validation_step_mock.assert_not_called()

    @patch("core.tasks.document_categorization.acquire_task_lock", return_value="lock-token")
    @patch("core.tasks.document_categorization.release_task_lock")
    @patch("core.tasks.document_categorization.default_storage.open")
    @patch("core.tasks.document_categorization.get_document_types_for_prompt")
    @patch("core.tasks.document_categorization.AIDocumentCategorizer.categorize_file_two_pass")
    @patch("core.tasks.document_categorization._run_validation_step")
    def test_matched_slot_runs_validation_when_doc_type_ai_validation_enabled(
        self,
        run_validation_step_mock,
        categorize_file_mock,
        get_types_mock,
        storage_open_mock,
        _release_lock_mock,
        _acquire_lock_mock,
    ):
        # Create an application document slot of the same type.
        Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type,
            created_by=self.user,
        )

        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"fake-file-bytes"
        get_types_mock.return_value = [{"id": self.doc_type.id, "name": self.doc_type.name}]
        categorize_file_mock.return_value = {
            "document_type_id": self.doc_type.id,
            "document_type": self.doc_type.name,
            "confidence": 0.95,
            "reasoning": "Looks like a passport.",
            "pass_used": 1,
        }

        _run_huey_task(run_document_categorization_item, item_id=str(self.item.id))

        self.item.refresh_from_db()
        self.assertEqual(self.item.status, DocumentCategorizationItem.STATUS_CATEGORIZED)
        self.assertIsNotNone(self.item.document_id)
        self.assertEqual(self.item.result.get("ai_validation_enabled"), True)
        run_validation_step_mock.assert_called_once()

    @patch("core.tasks.document_categorization.AIDocumentCategorizer.validate_document")
    def test_validation_timeout_skips_ai_validation_without_marking_invalid(self, validate_document_mock):
        validate_document_mock.side_effect = AIConnectionError(
            "AI slow response", error_code="timeout", is_timeout=True
        )

        self.item.result = {"stage": "validating", "ai_validation_enabled": True}
        self.item.save(update_fields=["result", "updated_at"])

        _run_validation_step(
            item=self.item,
            file_bytes=b"fake-file-bytes",
            doc_type=self.doc_type,
            document_types=[{"id": self.doc_type.id, "name": self.doc_type.name}],
            provider_order=None,
            product_prompt="",
        )

        self.item.refresh_from_db()
        self.assertEqual(self.item.validation_status, "")
        self.assertIsNone(self.item.validation_result)
        self.assertEqual(self.item.result.get("stage"), "categorized")
        self.assertFalse(self.item.result.get("ai_validation_enabled"))
        self.assertEqual(self.item.result.get("validation_skipped_reason"), "ai_timeout")
        self.assertEqual(self.item.result.get("validation_skipped_message"), "AI slow response")

    @patch("core.tasks.document_categorization.acquire_task_lock", return_value="lock-token")
    @patch("core.tasks.document_categorization.release_task_lock")
    @patch("core.tasks.document_categorization.default_storage.open")
    @patch("core.tasks.document_categorization.get_document_types_for_prompt")
    @patch("core.tasks.document_categorization.AIDocumentCategorizer.categorize_file_two_pass")
    def test_transient_categorization_failure_raises_retry_without_marking_item_error(
        self,
        categorize_file_mock,
        get_types_mock,
        storage_open_mock,
        _release_lock_mock,
        _acquire_lock_mock,
    ):
        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"fake-file-bytes"
        get_types_mock.return_value = [{"id": self.doc_type.id, "name": self.doc_type.name}]
        categorize_file_mock.side_effect = AIConnectionError(
            "AI slow response",
            error_code="timeout",
            is_timeout=True,
        )

        with self.assertRaises(dramatiq.Retry):
            run_document_categorization_item.actor.fn(item_id=str(self.item.id))

        self.item.refresh_from_db()
        self.assertEqual(self.item.status, DocumentCategorizationItem.STATUS_PROCESSING)
        self.assertEqual(self.item.result.get("stage"), "retrying")
        self.assertEqual(self.item.result.get("retryable_error"), "AI slow response")
