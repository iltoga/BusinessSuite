from unittest.mock import patch

from api.views_categorization import _upload_files_to_job
from customer_applications.models import DocApplication, DocumentCategorizationItem, DocumentCategorizationJob
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from products.models import Product


class DocumentCategorizationUploadParallelDispatchTests(TestCase):
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
        self.user = user_model.objects.create_user(username="cat-upload-user", password="testpass")
        self.customer = Customer.objects.create(customer_type="person", first_name="Cat", last_name="Upload")
        self.product = Product.objects.create(name="Categorization Product", code="CAT-UP", product_type="visa")
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )
        self.job = DocumentCategorizationJob.objects.create(
            doc_application=self.application,
            total_files=2,
            created_by=self.user,
        )

    @patch("api.views_categorization.run_document_categorization_item.delay")
    @patch("api.views_categorization.default_storage.save")
    def test_upload_multiple_dispatches_one_async_task_per_file(self, storage_save_mock, task_delay_mock):
        storage_save_mock.side_effect = lambda path, _file: path

        files = [
            SimpleUploadedFile("first.pdf", b"first-content"),
            SimpleUploadedFile("second.pdf", b"second-content"),
        ]

        uploaded_files, dispatched_tasks = _upload_files_to_job(job=self.job, files=files)

        self.assertEqual(uploaded_files, 2)
        self.assertEqual(dispatched_tasks, 2)
        self.assertEqual(storage_save_mock.call_count, 2)
        self.assertEqual(task_delay_mock.call_count, 2)

        items = list(DocumentCategorizationItem.objects.filter(job=self.job).order_by("sort_index"))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].filename, "first.pdf")
        self.assertEqual(items[1].filename, "second.pdf")
        self.assertEqual(items[0].result.get("stage"), "uploaded")
        self.assertEqual(items[1].result.get("stage"), "uploaded")

        delayed_ids = [call.args[0] for call in task_delay_mock.call_args_list]
        self.assertEqual(delayed_ids, [str(items[0].id), str(items[1].id)])
