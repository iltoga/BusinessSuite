"""Regression tests for applying document categorization actions."""

import json
from datetime import date
from unittest.mock import call, patch

from customer_applications.models import DocApplication, Document, DocumentCategorizationItem, DocumentCategorizationJob
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
            has_doc_number=True,
            has_details=True,
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
                "extracted_doc_number": "ITK-BULK-100",
                "extracted_details_markdown": "## ITK\n- Permit Number: ITK-BULK-100",
            },
        )

    @patch("api.views_categorization.default_storage.listdir", return_value=([], []))
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
        _storage_listdir_mock,
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
        self.assertEqual(self.document.doc_number, "ITK-BULK-100")
        self.assertEqual(self.document.details, "## ITK\n- Permit Number: ITK-BULK-100")
        self.assertEqual(self.document.ai_validation_status, Document.AI_VALIDATION_VALID)
        self.assertTrue(self.document.ai_validation)
        self.assertEqual(self.document.ai_validation_result, self.item.validation_result)

    def test_apply_rejects_job_while_validation_is_still_running(self):
        self.item.validation_status = ""
        self.item.validation_result = None
        self.item.result = {
            "document_type": self.doc_type.name,
            "document_type_id": self.doc_type.id,
            "confidence": 0.97,
            "reasoning": "Looks like ITK.",
            "pass_used": 1,
            "ai_validation_enabled": True,
            "stage": "validating",
        }
        self.item.save(update_fields=["validation_status", "validation_result", "result", "updated_at"])

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

        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertEqual(body["error"]["code"], "processing_incomplete")
        self.assertIn("still running", body["error"]["message"])
        self.assertIn("still running", body["error"]["details"]["detail"][0])


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class TransientFileCleanupTests(TestCase):
    """Tests that all transient files in tmp/categorization/{job_id}/ are
    removed after apply — including unapplied, no-slot, and errored items."""

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="cleanup_user",
            email="cleanup@example.com",
            password="password",
        )
        self.client.force_login(self.user)

        self.customer = Customer.objects.create(customer_type="person", first_name="Cleanup", last_name="Test")
        self.product = Product.objects.create(name="Cleanup Product", code="CLN-01", product_type="visa")
        self.doc_type_itk = DocumentType.objects.create(
            name="ITK Cleanup",
            ai_validation=True,
            has_expiration_date=True,
            has_doc_number=True,
        )
        self.doc_type_selfie = DocumentType.objects.create(
            name="Selfie Cleanup",
            ai_validation=True,
            has_file=True,
        )
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )
        self.doc_itk = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type_itk,
            created_by=self.user,
        )
        self.doc_selfie = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type_selfie,
            created_by=self.user,
        )
        self.job = DocumentCategorizationJob.objects.create(
            doc_application=self.application,
            total_files=3,
            created_by=self.user,
        )
        # Item 1: matched — will be applied
        self.item_matched = DocumentCategorizationItem.objects.create(
            job=self.job,
            sort_index=0,
            filename="itk.pdf",
            file_path=f"tmp/categorization/{self.job.id}/itk.pdf",
            status=DocumentCategorizationItem.STATUS_CATEGORIZED,
            document_type=self.doc_type_itk,
            document=self.doc_itk,
            validation_status="valid",
            validation_result={"valid": True, "confidence": 0.95},
        )
        # Item 2: no slot — will NOT be applied
        self.item_no_slot = DocumentCategorizationItem.objects.create(
            job=self.job,
            sort_index=1,
            filename="evoa.pdf",
            file_path=f"tmp/categorization/{self.job.id}/evoa.pdf",
            status=DocumentCategorizationItem.STATUS_CATEGORIZED,
            document_type=None,
            document=None,
            validation_status="",
            validation_result=None,
            result={"stage": "categorized", "validation_skipped_reason": "no_slot"},
        )
        # Item 3: error — will NOT be applied
        self.item_error = DocumentCategorizationItem.objects.create(
            job=self.job,
            sort_index=2,
            filename="corrupt.jpg",
            file_path=f"tmp/categorization/{self.job.id}/corrupt.jpg",
            status=DocumentCategorizationItem.STATUS_ERROR,
            error_message="AI timeout",
        )

    def _apply_url(self):
        return reverse("api-categorization-apply", kwargs={"job_id": str(self.job.id)})

    @patch("api.views_categorization.default_storage.listdir", return_value=([], []))
    @patch("api.views_categorization.default_storage.delete")
    @patch("api.views_categorization.default_storage.exists", return_value=True)
    @patch("api.views_categorization.default_storage.save", side_effect=lambda path, _content: path)
    @patch("api.views_categorization.default_storage.open")
    def test_apply_deletes_all_transient_files_including_unapplied(
        self,
        storage_open_mock,
        _storage_save_mock,
        storage_exists_mock,
        storage_delete_mock,
        _storage_listdir_mock,
    ):
        """After applying only the matched item, all three transient files
        (matched, no-slot, error) must be deleted from storage."""
        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"file-bytes"

        payload = {
            "mappings": [
                {
                    "item_id": str(self.item_matched.id),
                    "document_id": self.doc_itk.id,
                }
            ]
        }
        response = self.client.post(self._apply_url(), data=json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["totalApplied"], 1)

        # Verify all three temp files were passed to delete
        deleted_paths = [c.args[0] for c in storage_delete_mock.call_args_list]
        self.assertIn(self.item_matched.file_path, deleted_paths)
        self.assertIn(self.item_no_slot.file_path, deleted_paths)
        self.assertIn(self.item_error.file_path, deleted_paths)

    @patch("api.views_categorization.default_storage.listdir", return_value=([], []))
    @patch("api.views_categorization.default_storage.delete")
    @patch("api.views_categorization.default_storage.exists", return_value=True)
    @patch("api.views_categorization.default_storage.save", side_effect=lambda path, _content: path)
    @patch("api.views_categorization.default_storage.open")
    def test_apply_cleans_temp_folder_directory(
        self,
        storage_open_mock,
        _storage_save_mock,
        storage_exists_mock,
        storage_delete_mock,
        _storage_listdir_mock,
    ):
        """The temp folder tmp/categorization/{job_id} should be deleted after apply."""
        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"file-bytes"

        payload = {
            "mappings": [
                {
                    "item_id": str(self.item_matched.id),
                    "document_id": self.doc_itk.id,
                }
            ]
        }
        response = self.client.post(self._apply_url(), data=json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200, response.content)

        # The temp folder path itself should be passed to delete
        temp_dir = f"tmp/categorization/{self.job.id}"
        deleted_paths = [c.args[0] for c in storage_delete_mock.call_args_list]
        self.assertIn(temp_dir, deleted_paths)

    @patch("api.views_categorization.default_storage.listdir")
    @patch("api.views_categorization.default_storage.delete")
    @patch("api.views_categorization.default_storage.exists", return_value=True)
    @patch("api.views_categorization.default_storage.save", side_effect=lambda path, _content: path)
    @patch("api.views_categorization.default_storage.open")
    def test_apply_cleans_untracked_leftover_files_in_temp_folder(
        self,
        storage_open_mock,
        _storage_save_mock,
        storage_exists_mock,
        storage_delete_mock,
        storage_listdir_mock,
    ):
        """Files in the temp folder but not tracked by any item are also cleaned."""
        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"file-bytes"

        temp_dir = f"tmp/categorization/{self.job.id}"
        # listdir returns an untracked leftover file
        storage_listdir_mock.return_value = ([], ["untracked_orphan.pdf"])

        payload = {
            "mappings": [
                {
                    "item_id": str(self.item_matched.id),
                    "document_id": self.doc_itk.id,
                }
            ]
        }
        response = self.client.post(self._apply_url(), data=json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200, response.content)

        deleted_paths = [c.args[0] for c in storage_delete_mock.call_args_list]
        self.assertIn(f"{temp_dir}/untracked_orphan.pdf", deleted_paths)

    @patch("api.views_categorization.default_storage.listdir", return_value=([], []))
    @patch("api.views_categorization.default_storage.delete")
    @patch("api.views_categorization.default_storage.exists", return_value=True)
    @patch("api.views_categorization.default_storage.save", side_effect=lambda path, _content: path)
    @patch("api.views_categorization.default_storage.open")
    def test_apply_with_empty_mappings_still_cleans_all_transient_files(
        self,
        storage_open_mock,
        _storage_save_mock,
        storage_exists_mock,
        storage_delete_mock,
        _storage_listdir_mock,
    ):
        """When the user dismisses all files (applies with empty mappings),
        all transient files must still be deleted."""
        payload = {"mappings": []}
        response = self.client.post(self._apply_url(), data=json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["totalApplied"], 0)

        # All three temp files + temp dir should be cleaned
        deleted_paths = [c.args[0] for c in storage_delete_mock.call_args_list]
        self.assertIn(self.item_matched.file_path, deleted_paths)
        self.assertIn(self.item_no_slot.file_path, deleted_paths)
        self.assertIn(self.item_error.file_path, deleted_paths)

    @patch("api.views_categorization.default_storage.listdir", return_value=([], []))
    @patch("api.views_categorization.default_storage.delete")
    @patch("api.views_categorization.default_storage.exists", return_value=True)
    @patch("api.views_categorization.default_storage.save", side_effect=lambda path, _content: path)
    @patch("api.views_categorization.default_storage.open")
    def test_cleanup_is_resilient_to_individual_file_delete_failure(
        self,
        storage_open_mock,
        _storage_save_mock,
        storage_exists_mock,
        storage_delete_mock,
        _storage_listdir_mock,
    ):
        """If one file delete fails, other files should still be cleaned up."""
        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"file-bytes"

        # Make delete raise for the first item but succeed for others
        def selective_delete(path):
            if path == self.item_matched.file_path:
                raise OSError("Simulated storage error")

        storage_delete_mock.side_effect = selective_delete

        payload = {
            "mappings": [
                {
                    "item_id": str(self.item_matched.id),
                    "document_id": self.doc_itk.id,
                }
            ]
        }
        response = self.client.post(self._apply_url(), data=json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200, response.content)

        # Despite the error, cleanup was attempted for all files
        deleted_paths = [c.args[0] for c in storage_delete_mock.call_args_list]
        self.assertIn(self.item_matched.file_path, deleted_paths)
        self.assertIn(self.item_no_slot.file_path, deleted_paths)
        self.assertIn(self.item_error.file_path, deleted_paths)

    @patch("api.views_categorization.default_storage.listdir", return_value=([], []))
    @patch("api.views_categorization.default_storage.delete")
    @patch("api.views_categorization.default_storage.exists", return_value=True)
    @patch("api.views_categorization.default_storage.save", side_effect=lambda path, _content: path)
    @patch("api.views_categorization.default_storage.open")
    def test_applied_file_persisted_at_final_path_only(
        self,
        storage_open_mock,
        storage_save_mock,
        _storage_exists_mock,
        storage_delete_mock,
        _storage_listdir_mock,
    ):
        """The applied file must be saved to the canonical Document path,
        and the temp copy must be deleted — only the final copy persists."""
        storage_open_mock.return_value.__enter__.return_value.read.return_value = b"file-bytes"

        payload = {
            "mappings": [
                {
                    "item_id": str(self.item_matched.id),
                    "document_id": self.doc_itk.id,
                }
            ]
        }
        response = self.client.post(self._apply_url(), data=json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200, response.content)

        # The file was saved to the final Document path
        save_calls = storage_save_mock.call_args_list
        saved_paths = [c.args[0] for c in save_calls]
        expected_final_path = f"{self.application.upload_folder}/ITK_Cleanup.pdf"
        self.assertTrue(
            any(expected_final_path in p for p in saved_paths),
            f"Expected final path '{expected_final_path}' among saved paths {saved_paths}",
        )

        # The transient file was deleted
        deleted_paths = [c.args[0] for c in storage_delete_mock.call_args_list]
        self.assertIn(self.item_matched.file_path, deleted_paths)
