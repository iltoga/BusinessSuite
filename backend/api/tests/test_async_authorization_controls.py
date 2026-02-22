from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.async_controls import build_guard_counter_key
from core.tasks import cron_jobs
from core.models import AsyncJob, DocumentOCRJob, OCRJob
from customers.models import Customer
from invoices.models import Invoice, InvoiceDownloadJob, InvoiceImportJob

User = get_user_model()


class CronExecAuthorizationTests(TestCase):
    def setUp(self):
        cron_jobs.reset_privileged_cron_job_locks()
        self.staff_user = User.objects.create_user("cron-staff", "cron-staff@example.com", "pass", is_staff=True)
        self.regular_user = User.objects.create_user("cron-user", "cron-user@example.com", "pass")
        admin_group = Group.objects.create(name="admin")
        self.admin_group_user = User.objects.create_user("cron-admin", "cron-admin@example.com", "pass")
        self.admin_group_user.groups.add(admin_group)

        self.staff_client = APIClient()
        self.staff_client.force_authenticate(self.staff_user)

        self.admin_group_client = APIClient()
        self.admin_group_client.force_authenticate(self.admin_group_user)

        self.regular_client = APIClient()
        self.regular_client.force_authenticate(self.regular_user)

        self.unauthenticated_client = APIClient()

    def tearDown(self):
        cron_jobs.reset_privileged_cron_job_locks()
        cache.clear()

    @patch("api.views.enqueue_clear_cache_now", return_value=True)
    @patch("api.views.enqueue_full_backup_now", return_value=True)
    def test_exec_cron_jobs_requires_staff_or_admin_permissions(self, backup_enqueue_mock, clear_cache_enqueue_mock):
        url = reverse("api-exec-cron-jobs")

        unauthenticated_response = self.unauthenticated_client.get(url)
        self.assertIn(unauthenticated_response.status_code, {401, 403})

        regular_response = self.regular_client.get(url)
        self.assertEqual(regular_response.status_code, 403)

        staff_response = self.staff_client.get(url)
        self.assertEqual(staff_response.status_code, 202)
        self.assertEqual(staff_response.data["status"], "queued")
        self.assertEqual(staff_response.data["fullBackupQueued"], True)
        self.assertEqual(staff_response.data["clearCacheQueued"], True)
        backup_enqueue_mock.assert_called_once()
        clear_cache_enqueue_mock.assert_called_once()

    @patch("api.views.enqueue_clear_cache_now", side_effect=[True, False])
    @patch("api.views.enqueue_full_backup_now", side_effect=[True, False])
    def test_exec_cron_jobs_returns_already_queued_on_duplicate_trigger(
        self, backup_enqueue_mock, clear_cache_enqueue_mock
    ):
        url = reverse("api-exec-cron-jobs")

        first_response = self.staff_client.get(url)
        self.assertEqual(first_response.status_code, 202)
        self.assertEqual(first_response.data["status"], "queued")
        self.assertEqual(first_response.data["fullBackupQueued"], True)
        self.assertEqual(first_response.data["clearCacheQueued"], True)

        second_response = self.staff_client.get(url)
        self.assertEqual(second_response.status_code, 202)
        self.assertEqual(second_response.data["status"], "already_queued")
        self.assertEqual(second_response.data["fullBackupQueued"], False)
        self.assertEqual(second_response.data["clearCacheQueued"], False)

        self.assertEqual(backup_enqueue_mock.call_count, 2)
        self.assertEqual(clear_cache_enqueue_mock.call_count, 2)

    @patch("api.views.enqueue_clear_cache_now", return_value=True)
    @patch("api.views.enqueue_full_backup_now", return_value=True)
    def test_exec_cron_jobs_allows_admin_group_members(self, backup_enqueue_mock, clear_cache_enqueue_mock):
        url = reverse("api-exec-cron-jobs")

        response = self.admin_group_client.get(url)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "queued")
        self.assertEqual(response.data["fullBackupQueued"], True)
        self.assertEqual(response.data["clearCacheQueued"], True)
        backup_enqueue_mock.assert_called_once()
        clear_cache_enqueue_mock.assert_called_once()


class AsyncOwnershipAuthorizationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com", "pass")
        self.other = User.objects.create_user("other", "other@example.com", "pass")
        self.owner_token = Token.objects.create(user=self.owner)
        self.other_token = Token.objects.create(user=self.other)

        self.owner_client = APIClient()
        self.owner_client.force_authenticate(self.owner)

        self.other_client = APIClient()
        self.other_client.force_authenticate(self.other)

    def test_async_job_list_and_retrieve_are_owner_scoped(self):
        own_job = AsyncJob.objects.create(task_name="own", created_by=self.owner)
        other_job = AsyncJob.objects.create(task_name="other", created_by=self.other)

        list_response = self.owner_client.get("/api/async-jobs/")
        self.assertEqual(list_response.status_code, 200)
        rows = list_response.data.get("results", []) if hasattr(list_response.data, "get") else list_response.data
        listed_ids = {item["id"] for item in rows}
        self.assertIn(str(own_job.id), listed_ids)
        self.assertNotIn(str(other_job.id), listed_ids)

        own_retrieve = self.owner_client.get(f"/api/async-jobs/{own_job.id}/")
        self.assertEqual(own_retrieve.status_code, 200)

        other_retrieve = self.owner_client.get(f"/api/async-jobs/{other_job.id}/")
        self.assertEqual(other_retrieve.status_code, 404)

    def test_async_job_status_sse_is_owner_scoped(self):
        job = AsyncJob.objects.create(task_name="export", created_by=self.owner)
        sse_url = reverse("api-async-job-status-sse", kwargs={"job_id": str(job.id)})

        forbidden_client = APIClient()
        forbidden_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.other_token.key}")
        forbidden_response = forbidden_client.get(sse_url)
        self.assertEqual(forbidden_response.status_code, 404)

        allowed_client = APIClient()
        allowed_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.owner_token.key}")
        allowed_response = allowed_client.get(sse_url)
        self.assertEqual(allowed_response.status_code, 200)
        self.assertTrue(allowed_response.get("Content-Type", "").startswith("text/event-stream"))

    def test_ocr_status_endpoint_is_owner_scoped(self):
        ocr_job = OCRJob.objects.create(
            status=OCRJob.STATUS_QUEUED,
            progress=0,
            file_path="tmpfiles/ocr-test.pdf",
            file_url="/uploads/tmpfiles/ocr-test.pdf",
            created_by=self.owner,
        )

        denied = self.other_client.get(reverse("api-ocr-status", kwargs={"job_id": str(ocr_job.id)}))
        self.assertEqual(denied.status_code, 404)

        allowed = self.owner_client.get(reverse("api-ocr-status", kwargs={"job_id": str(ocr_job.id)}))
        self.assertEqual(allowed.status_code, 200)

    def test_document_ocr_status_endpoint_is_owner_scoped(self):
        document_job = DocumentOCRJob.objects.create(
            status=DocumentOCRJob.STATUS_QUEUED,
            progress=0,
            file_path="tmpfiles/document-ocr-test.pdf",
            file_url="/uploads/tmpfiles/document-ocr-test.pdf",
            created_by=self.owner,
        )

        denied = self.other_client.get(reverse("api-document-ocr-status", kwargs={"job_id": str(document_job.id)}))
        self.assertEqual(denied.status_code, 404)

        allowed = self.owner_client.get(reverse("api-document-ocr-status", kwargs={"job_id": str(document_job.id)}))
        self.assertEqual(allowed.status_code, 200)

    def test_invoice_import_status_endpoint_is_owner_scoped(self):
        import_job = InvoiceImportJob.objects.create(
            status=InvoiceImportJob.STATUS_QUEUED,
            progress=0,
            total_files=1,
            created_by=self.owner,
        )

        denied = self.other_client.get(reverse("invoices-import-status", kwargs={"job_id": str(import_job.id)}))
        self.assertEqual(denied.status_code, 404)

        allowed = self.owner_client.get(reverse("invoices-import-status", kwargs={"job_id": str(import_job.id)}))
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data["jobId"], str(import_job.id))

    def test_invoice_import_stream_endpoint_is_owner_scoped(self):
        import_job = InvoiceImportJob.objects.create(
            status=InvoiceImportJob.STATUS_QUEUED,
            progress=0,
            total_files=1,
            created_by=self.owner,
        )

        denied = self.other_client.get(f"/api/invoices/import/stream/{import_job.id}/")
        self.assertEqual(denied.status_code, 404)

    def test_invoice_download_status_endpoint_is_owner_scoped(self):
        customer = Customer.objects.create(first_name="Jane", last_name="Owner")
        invoice = Invoice.objects.create(
            customer=customer,
            invoice_date=date.today(),
            due_date=date.today(),
            created_by=self.owner,
            updated_by=self.owner,
        )
        download_job = InvoiceDownloadJob.objects.create(
            invoice=invoice,
            status=InvoiceDownloadJob.STATUS_QUEUED,
            progress=0,
            created_by=self.owner,
        )

        denied = self.other_client.get(reverse("invoices-download-async-status", kwargs={"job_id": str(download_job.id)}))
        self.assertEqual(denied.status_code, 404)

        allowed = self.owner_client.get(reverse("invoices-download-async-status", kwargs={"job_id": str(download_job.id)}))
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data["job_id"], str(download_job.id))

    def test_invoice_download_stream_endpoint_is_owner_scoped(self):
        customer = Customer.objects.create(first_name="Jake", last_name="Owner")
        invoice = Invoice.objects.create(
            customer=customer,
            invoice_date=date.today(),
            due_date=date.today(),
            created_by=self.owner,
            updated_by=self.owner,
        )
        download_job = InvoiceDownloadJob.objects.create(
            invoice=invoice,
            status=InvoiceDownloadJob.STATUS_QUEUED,
            progress=0,
            created_by=self.owner,
        )

        denied = self.other_client.get(reverse("invoices-download-async-stream", kwargs={"job_id": str(download_job.id)}))
        self.assertEqual(denied.status_code, 404)


class ExpensiveAsyncEnqueueIdempotencyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("async-user", "async-user@example.com", "pass")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def tearDown(self):
        cache.clear()

    @patch("products.tasks.run_product_export_job")
    def test_product_export_start_reuses_existing_inflight_job(self, enqueue_mock):
        first = self.client.post("/api/products/export/start/", {"search_query": "visa"}, format="json")
        self.assertEqual(first.status_code, 202)
        first_job_id = first.data["job_id"]
        self.assertTrue(first.data["queued"])
        enqueue_mock.assert_called_once()

        second = self.client.post("/api/products/export/start/", {"search_query": "visa"}, format="json")
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.data["job_id"], first_job_id)
        self.assertFalse(second.data["queued"])
        self.assertTrue(second.data["deduplicated"])
        self.assertEqual(AsyncJob.objects.filter(task_name="products_export_excel", created_by=self.user).count(), 1)
        enqueue_mock.assert_called_once()
        dedupe_counter_key = build_guard_counter_key(namespace="products_export_excel", event="deduplicated")
        self.assertEqual(cache.get(dedupe_counter_key), 1)

    @patch("api.views._latest_inflight_job", return_value=None)
    @patch("api.views._get_enqueue_guard_token", return_value=("guard:lock:key", None))
    def test_product_export_start_records_lock_contention_and_429_observability(self, _guard_token_mock, _inflight_mock):
        response = self.client.post("/api/products/export/start/", {"search_query": "visa"}, format="json")

        self.assertEqual(response.status_code, 429)
        lock_counter_key = build_guard_counter_key(namespace="products_export_excel", event="lock_contention")
        rate_limit_counter_key = build_guard_counter_key(namespace="products_export_excel", event="guard_429")
        self.assertEqual(cache.get(lock_counter_key), 1)
        self.assertEqual(cache.get(rate_limit_counter_key), 1)

    @patch("api.views.default_storage.save", return_value="tmpfiles/product_imports/mock.xlsx")
    @patch("products.tasks.run_product_import_job")
    def test_product_import_start_reuses_existing_inflight_job(self, enqueue_mock, storage_save_mock):
        upload_one = SimpleUploadedFile(
            "products.xlsx",
            b"dummy-bytes",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        first = self.client.post("/api/products/import/start/", {"file": upload_one}, format="multipart")
        self.assertEqual(first.status_code, 202)
        first_job_id = first.data["job_id"]
        self.assertTrue(first.data["queued"])
        enqueue_mock.assert_called_once()

        upload_two = SimpleUploadedFile(
            "products.xlsx",
            b"dummy-bytes-2",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        second = self.client.post("/api/products/import/start/", {"file": upload_two}, format="multipart")
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.data["job_id"], first_job_id)
        self.assertFalse(second.data["queued"])
        self.assertTrue(second.data["deduplicated"])
        self.assertEqual(AsyncJob.objects.filter(task_name="products_import_excel", created_by=self.user).count(), 1)
        enqueue_mock.assert_called_once()
        storage_save_mock.assert_called_once()

    @patch("api.views.run_invoice_download_job")
    def test_invoice_download_async_reuses_existing_inflight_job(self, enqueue_mock):
        customer = Customer.objects.create(first_name="Download", last_name="Owner")
        invoice = Invoice.objects.create(
            customer=customer,
            invoice_date=date.today(),
            due_date=date.today(),
            created_by=self.user,
            updated_by=self.user,
        )

        first = self.client.post(f"/api/invoices/{invoice.id}/download-async/", {"file_format": "pdf"}, format="json")
        self.assertEqual(first.status_code, 202)
        first_job_id = first.data["job_id"]
        self.assertTrue(first.data["queued"])
        enqueue_mock.assert_called_once()

        second = self.client.post(f"/api/invoices/{invoice.id}/download-async/", {"file_format": "pdf"}, format="json")
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.data["job_id"], first_job_id)
        self.assertFalse(second.data["queued"])
        self.assertTrue(second.data["deduplicated"])
        self.assertEqual(InvoiceDownloadJob.objects.filter(invoice=invoice, created_by=self.user).count(), 1)
        enqueue_mock.assert_called_once()

    @patch("api.views.default_storage.url", return_value="/uploads/tmpfiles/passport.png")
    @patch("api.views.default_storage.save", return_value="tmpfiles/passport.png")
    @patch("api.views.run_ocr_job")
    def test_passport_ocr_check_reuses_existing_inflight_job(self, enqueue_mock, storage_save_mock, storage_url_mock):
        passport_one = SimpleUploadedFile("passport.png", b"png-bytes", content_type="image/png")
        first = self.client.post("/api/ocr/check/", {"file": passport_one, "doc_type": "passport"}, format="multipart")
        self.assertEqual(first.status_code, 202)
        first_job_id = first.data["job_id"]
        self.assertTrue(first.data["queued"])
        enqueue_mock.assert_called_once()

        passport_two = SimpleUploadedFile("passport.png", b"png-bytes-2", content_type="image/png")
        second = self.client.post("/api/ocr/check/", {"file": passport_two, "doc_type": "passport"}, format="multipart")
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.data["job_id"], first_job_id)
        self.assertFalse(second.data["queued"])
        self.assertTrue(second.data["deduplicated"])
        self.assertEqual(OCRJob.objects.filter(created_by=self.user).count(), 1)
        enqueue_mock.assert_called_once()
        storage_save_mock.assert_called_once()
        storage_url_mock.assert_called_once()

    @patch("api.views.default_storage.url", return_value="/uploads/tmpfiles/document.pdf")
    @patch("api.views.default_storage.save", return_value="tmpfiles/document.pdf")
    @patch("api.views.run_document_ocr_job")
    def test_document_ocr_check_reuses_existing_inflight_job(
        self, enqueue_mock, storage_save_mock, storage_url_mock
    ):
        document_one = SimpleUploadedFile("document.pdf", b"pdf-bytes", content_type="application/pdf")
        first = self.client.post("/api/document-ocr/check/", {"file": document_one}, format="multipart")
        self.assertEqual(first.status_code, 202)
        first_job_id = first.data["job_id"]
        self.assertTrue(first.data["queued"])
        enqueue_mock.assert_called_once()

        document_two = SimpleUploadedFile("document.pdf", b"pdf-bytes-2", content_type="application/pdf")
        second = self.client.post("/api/document-ocr/check/", {"file": document_two}, format="multipart")
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.data["job_id"], first_job_id)
        self.assertFalse(second.data["queued"])
        self.assertTrue(second.data["deduplicated"])
        self.assertEqual(DocumentOCRJob.objects.filter(created_by=self.user).count(), 1)
        enqueue_mock.assert_called_once()
        storage_save_mock.assert_called_once()
        storage_url_mock.assert_called_once()

    @patch("api.views.default_storage.save", return_value="tmpfiles/invoice_imports/mock.pdf")
    @patch("invoices.tasks.import_jobs.run_invoice_import_item")
    def test_invoice_import_batch_reuses_existing_inflight_job(self, enqueue_mock, storage_save_mock):
        file_one = SimpleUploadedFile("invoice-one.pdf", b"pdf-bytes", content_type="application/pdf")
        first = self.client.post(
            "/api/invoices/import/batch/",
            {"files": [file_one], "paid_status": ["false"]},
            format="multipart",
        )
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.get("Content-Type", "").startswith("text/event-stream"))
        self.assertEqual(InvoiceImportJob.objects.filter(created_by=self.user).count(), 1)
        enqueue_mock.assert_called_once()

        file_two = SimpleUploadedFile("invoice-two.pdf", b"pdf-bytes-2", content_type="application/pdf")
        second = self.client.post(
            "/api/invoices/import/batch/",
            {"files": [file_two], "paid_status": ["true"]},
            format="multipart",
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.get("Content-Type", "").startswith("text/event-stream"))
        self.assertEqual(InvoiceImportJob.objects.filter(created_by=self.user).count(), 1)
        enqueue_mock.assert_called_once()
        storage_save_mock.assert_called_once()
