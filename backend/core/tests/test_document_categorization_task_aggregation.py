from core.tasks.document_categorization import _update_categorization_job_counts
from customer_applications.models import DocApplication, DocumentCategorizationItem, DocumentCategorizationJob
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from products.models import Product


class DocumentCategorizationTaskAggregationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="cat-agg-user", password="testpass")
        self.customer = Customer.objects.create(customer_type="person", first_name="Cat", last_name="Agg")
        self.product = Product.objects.create(name="Categorization Product", code="CAT-AGG", product_type="visa")
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

    def test_empty_job_resets_stale_counters_and_completes(self):
        job = DocumentCategorizationJob.objects.create(
            doc_application=self.application,
            status=DocumentCategorizationJob.STATUS_PROCESSING,
            total_files=3,
            processed_files=2,
            success_count=1,
            error_count=1,
        )

        _update_categorization_job_counts(job.id)

        job.refresh_from_db()
        self.assertEqual(job.total_files, 0)
        self.assertEqual(job.processed_files, 0)
        self.assertEqual(job.success_count, 0)
        self.assertEqual(job.error_count, 0)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.status, DocumentCategorizationJob.STATUS_COMPLETED)

    def test_syncs_total_files_to_actual_items(self):
        job = DocumentCategorizationJob.objects.create(
            doc_application=self.application,
            status=DocumentCategorizationJob.STATUS_PROCESSING,
            total_files=99,
        )
        DocumentCategorizationItem.objects.create(
            job=job,
            sort_index=0,
            filename="one.pdf",
            file_path="tmp/one.pdf",
            status=DocumentCategorizationItem.STATUS_CATEGORIZED,
        )

        _update_categorization_job_counts(job.id)

        job.refresh_from_db()
        self.assertEqual(job.total_files, 1)
        self.assertEqual(job.processed_files, 1)
        self.assertEqual(job.success_count, 1)
        self.assertEqual(job.error_count, 0)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.status, DocumentCategorizationJob.STATUS_COMPLETED)

    def test_job_fails_when_all_items_error(self):
        job = DocumentCategorizationJob.objects.create(
            doc_application=self.application,
            status=DocumentCategorizationJob.STATUS_PROCESSING,
            total_files=2,
        )
        DocumentCategorizationItem.objects.create(
            job=job,
            sort_index=0,
            filename="one.pdf",
            file_path="tmp/one.pdf",
            status=DocumentCategorizationItem.STATUS_ERROR,
        )
        DocumentCategorizationItem.objects.create(
            job=job,
            sort_index=1,
            filename="two.pdf",
            file_path="tmp/two.pdf",
            status=DocumentCategorizationItem.STATUS_ERROR,
        )

        _update_categorization_job_counts(job.id)

        job.refresh_from_db()
        self.assertEqual(job.processed_files, 2)
        self.assertEqual(job.success_count, 0)
        self.assertEqual(job.error_count, 2)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.status, DocumentCategorizationJob.STATUS_FAILED)

    def test_job_stays_processing_until_all_items_terminal(self):
        job = DocumentCategorizationJob.objects.create(
            doc_application=self.application,
            status=DocumentCategorizationJob.STATUS_PROCESSING,
            total_files=2,
        )
        DocumentCategorizationItem.objects.create(
            job=job,
            sort_index=0,
            filename="one.pdf",
            file_path="tmp/one.pdf",
            status=DocumentCategorizationItem.STATUS_CATEGORIZED,
        )
        DocumentCategorizationItem.objects.create(
            job=job,
            sort_index=1,
            filename="two.pdf",
            file_path="tmp/two.pdf",
            status=DocumentCategorizationItem.STATUS_PROCESSING,
        )

        _update_categorization_job_counts(job.id)

        job.refresh_from_db()
        self.assertEqual(job.total_files, 2)
        self.assertEqual(job.processed_files, 1)
        self.assertEqual(job.success_count, 1)
        self.assertEqual(job.error_count, 0)
        self.assertEqual(job.progress, 50)
        self.assertEqual(job.status, DocumentCategorizationJob.STATUS_PROCESSING)

    def test_recompute_is_idempotent_on_retries(self):
        job = DocumentCategorizationJob.objects.create(
            doc_application=self.application,
            status=DocumentCategorizationJob.STATUS_PROCESSING,
            total_files=2,
        )
        DocumentCategorizationItem.objects.create(
            job=job,
            sort_index=0,
            filename="one.pdf",
            file_path="tmp/one.pdf",
            status=DocumentCategorizationItem.STATUS_CATEGORIZED,
        )
        DocumentCategorizationItem.objects.create(
            job=job,
            sort_index=1,
            filename="two.pdf",
            file_path="tmp/two.pdf",
            status=DocumentCategorizationItem.STATUS_ERROR,
        )

        _update_categorization_job_counts(job.id)
        _update_categorization_job_counts(job.id)

        job.refresh_from_db()
        self.assertEqual(job.total_files, 2)
        self.assertEqual(job.processed_files, 2)
        self.assertEqual(job.success_count, 1)
        self.assertEqual(job.error_count, 1)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.status, DocumentCategorizationJob.STATUS_COMPLETED)
