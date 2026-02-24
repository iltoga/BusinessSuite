from datetime import date
from unittest.mock import call, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from customer_applications.models import DocApplication, Document
from customer_applications.tasks import cleanup_document_storage_task
from customers.models import Customer
from products.models import DocumentType, Product

User = get_user_model()


def _run_task(task, **kwargs):
    if hasattr(task, "call_local"):
        return task.call_local(**kwargs)
    if hasattr(task, "func"):
        return task.func(**kwargs)
    return task(**kwargs)


class StorageCleanupOnDeleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "admin@example.com", "pass")
        self.customer = Customer.objects.create(first_name="Test", last_name="User")
        self.product = Product.objects.create(name="Test Product", code="TP-1")
        self.doc_type = DocumentType.objects.create(name="Passport", has_file=True)

    def _create_application(self):
        return DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 1, 1),
            created_by=self.user,
        )

    def _create_document(self, application, filename="passport.pdf"):
        return Document.objects.create(
            doc_application=application,
            doc_type=self.doc_type,
            file=f"{application.upload_folder}/{filename}",
            required=True,
            created_by=self.user,
        )

    def test_document_delete_queues_async_storage_cleanup(self):
        application = self._create_application()
        document = self._create_document(application)

        with (
            patch("django.db.transaction.on_commit", side_effect=lambda callback: callback()),
            patch("customer_applications.tasks.cleanup_document_storage_task") as cleanup_mock,
        ):
            document.delete()

        cleanup_mock.assert_called_once_with(
            file_path=f"{application.upload_folder}/passport.pdf",
            folder_path=application.upload_folder,
        )

    def test_application_delete_cascades_documents_and_queues_folder_cleanup(self):
        application = self._create_application()
        document = self._create_document(application)
        expected_folder = application.upload_folder

        with (
            patch("django.db.transaction.on_commit", side_effect=lambda callback: callback()),
            patch("customer_applications.tasks.sync_application_calendar_task"),
            patch("customer_applications.tasks.cleanup_application_storage_folder_task") as folder_cleanup_mock,
            patch("customer_applications.tasks.cleanup_document_storage_task"),
        ):
            application.delete()

        self.assertFalse(DocApplication.objects.filter(pk=application.pk).exists())
        self.assertFalse(Document.objects.filter(pk=document.pk).exists())
        folder_cleanup_mock.assert_called_once_with(folder_path=expected_folder)

    @patch("customer_applications.tasks.default_storage")
    def test_cleanup_document_task_deletes_file_and_empty_folder_marker(self, storage_mock):
        folder_path = "documents/test_user_1/application_1"
        file_path = f"{folder_path}/passport.pdf"
        storage_mock.exists.side_effect = lambda path: path in {file_path, f"{folder_path}/"}
        storage_mock.listdir.return_value = ([], [])

        _run_task(cleanup_document_storage_task, file_path=file_path, folder_path=folder_path)

        storage_mock.delete.assert_has_calls([call(file_path), call(f"{folder_path}/")])
