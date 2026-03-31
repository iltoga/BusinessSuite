"""Regression tests for customer upload folder sanitization."""

from pathlib import PurePosixPath

from customers.models import Customer
from django.test import TestCase, override_settings


@override_settings(DOCUMENTS_FOLDER="documents")
class CustomerUploadFolderSanitizationTests(TestCase):
    def test_upload_folder_does_not_allow_path_traversal_components(self):
        customer = Customer.objects.create(
            customer_type="person",
            first_name="../../etc",
            last_name="passwd",
            notify_by="Email",
        )

        upload_folder = customer.upload_folder
        parts = PurePosixPath(upload_folder).parts

        self.assertEqual(parts[0], "documents")
        self.assertNotIn("..", parts)
        self.assertNotIn("/", parts[-1])
        self.assertTrue(parts[-1].endswith(f"_{customer.pk}"))
