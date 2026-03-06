from datetime import date

from core.models import AsyncJob, DocumentOCRJob, OCRJob
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from invoices.models import Invoice, InvoiceDocumentJob, InvoiceDownloadJob, InvoiceImportJob

User = get_user_model()


class AsyncEnqueueIndexTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("queue-owner", "queue-owner@example.com", "pass")
        cls.other_user = User.objects.create_user("queue-other", "queue-other@example.com", "pass")
        customer = Customer.objects.create(first_name="Index", last_name="Probe")
        cls.invoice = Invoice.objects.create(
            customer=customer,
            invoice_date=date.today(),
            due_date=date.today(),
        )

        for status in (AsyncJob.STATUS_PENDING, AsyncJob.STATUS_PROCESSING, AsyncJob.STATUS_COMPLETED):
            AsyncJob.objects.create(task_name="products_export_excel", created_by=cls.user, status=status)
        AsyncJob.objects.create(task_name="other_task", created_by=cls.other_user, status=AsyncJob.STATUS_PENDING)

        for status in (OCRJob.STATUS_QUEUED, OCRJob.STATUS_PROCESSING, OCRJob.STATUS_COMPLETED):
            OCRJob.objects.create(
                created_by=cls.user,
                status=status,
                file_path=f"tmpfiles/ocr-{status}.pdf",
                file_url=f"/media/ocr-{status}.pdf",
            )
        OCRJob.objects.create(
            created_by=cls.other_user,
            status=OCRJob.STATUS_QUEUED,
            file_path="tmpfiles/ocr-other.pdf",
            file_url="/media/ocr-other.pdf",
        )

        for status in (DocumentOCRJob.STATUS_QUEUED, DocumentOCRJob.STATUS_PROCESSING, DocumentOCRJob.STATUS_COMPLETED):
            DocumentOCRJob.objects.create(
                created_by=cls.user,
                status=status,
                file_path=f"tmpfiles/document-ocr-{status}.pdf",
                file_url=f"/media/document-ocr-{status}.pdf",
            )
        DocumentOCRJob.objects.create(
            created_by=cls.other_user,
            status=DocumentOCRJob.STATUS_QUEUED,
            file_path="tmpfiles/document-ocr-other.pdf",
            file_url="/media/document-ocr-other.pdf",
        )

        for status in (
            InvoiceImportJob.STATUS_QUEUED,
            InvoiceImportJob.STATUS_PROCESSING,
            InvoiceImportJob.STATUS_COMPLETED,
        ):
            InvoiceImportJob.objects.create(created_by=cls.user, status=status, total_files=1)
        InvoiceImportJob.objects.create(created_by=cls.other_user, status=InvoiceImportJob.STATUS_QUEUED, total_files=1)

        for status in (
            InvoiceDownloadJob.STATUS_QUEUED,
            InvoiceDownloadJob.STATUS_PROCESSING,
            InvoiceDownloadJob.STATUS_COMPLETED,
        ):
            InvoiceDownloadJob.objects.create(
                invoice=cls.invoice,
                created_by=cls.user,
                status=status,
                format_type=InvoiceDownloadJob.FORMAT_PDF,
            )
        InvoiceDownloadJob.objects.create(
            invoice=cls.invoice,
            created_by=cls.other_user,
            status=InvoiceDownloadJob.STATUS_QUEUED,
            format_type=InvoiceDownloadJob.FORMAT_DOCX,
        )

        for status in (
            InvoiceDocumentJob.STATUS_QUEUED,
            InvoiceDocumentJob.STATUS_PROCESSING,
            InvoiceDocumentJob.STATUS_COMPLETED,
        ):
            InvoiceDocumentJob.objects.create(created_by=cls.user, status=status, format_type=InvoiceDocumentJob.FORMAT_DOCX)
        InvoiceDocumentJob.objects.create(
            created_by=cls.other_user,
            status=InvoiceDocumentJob.STATUS_QUEUED,
            format_type=InvoiceDocumentJob.FORMAT_PDF,
        )

    def _constraint_names(self, model):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, model._meta.db_table)
        return set(constraints.keys())

    def _sqlite_query_plan(self, queryset):
        sql, params = queryset.query.sql_with_params()
        with connection.cursor() as cursor:
            cursor.execute(f"EXPLAIN QUERY PLAN {sql}", params)
            return "\n".join(str(row[-1]) for row in cursor.fetchall())

    def test_expected_enqueue_indexes_exist(self):
        expected_indexes = {
            AsyncJob: "core_asyncjob_guard_idx",
            OCRJob: "core_ocrjob_guard_idx",
            DocumentOCRJob: "core_dococr_guard_idx",
            InvoiceImportJob: "inv_import_guard_idx",
            InvoiceDownloadJob: "inv_dl_guard_lookup_idx",
            InvoiceDocumentJob: "inv_doc_guard_lookup_idx",
        }

        for model, index_name in expected_indexes.items():
            with self.subTest(model=model.__name__):
                self.assertIn(index_name, self._constraint_names(model))

    def test_sqlite_query_planner_uses_enqueue_indexes(self):
        if connection.vendor != "sqlite":
            self.skipTest("Query plan assertion is tailored to the sqlite test database")

        querysets = {
            "async_job": (
                "core_asyncjob_guard_idx",
                AsyncJob.objects.filter(
                    task_name="products_export_excel",
                    created_by=self.user,
                    status__in=[AsyncJob.STATUS_PENDING, AsyncJob.STATUS_PROCESSING],
                )
                .order_by("-created_at", "-id")[:1],
            ),
            "ocr_job": (
                "core_ocrjob_guard_idx",
                OCRJob.objects.filter(
                    created_by=self.user,
                    status__in=[OCRJob.STATUS_QUEUED, OCRJob.STATUS_PROCESSING],
                )
                .order_by("-created_at", "-id")[:1],
            ),
            "document_ocr_job": (
                "core_dococr_guard_idx",
                DocumentOCRJob.objects.filter(
                    created_by=self.user,
                    status__in=[DocumentOCRJob.STATUS_QUEUED, DocumentOCRJob.STATUS_PROCESSING],
                )
                .order_by("-created_at", "-id")[:1],
            ),
            "invoice_import_job": (
                "inv_import_guard_idx",
                InvoiceImportJob.objects.filter(
                    created_by=self.user,
                    status__in=[InvoiceImportJob.STATUS_QUEUED, InvoiceImportJob.STATUS_PROCESSING],
                )
                .order_by("-created_at", "-id")[:1],
            ),
            "invoice_download_job": (
                "inv_dl_guard_lookup_idx",
                InvoiceDownloadJob.objects.filter(
                    invoice=self.invoice,
                    format_type=InvoiceDownloadJob.FORMAT_PDF,
                    created_by=self.user,
                    status__in=[InvoiceDownloadJob.STATUS_QUEUED, InvoiceDownloadJob.STATUS_PROCESSING],
                )
                .order_by("-created_at", "-id")[:1],
            ),
            "invoice_document_job": (
                "inv_doc_guard_lookup_idx",
                InvoiceDocumentJob.objects.filter(
                    created_by=self.user,
                    status__in=[InvoiceDocumentJob.STATUS_QUEUED, InvoiceDocumentJob.STATUS_PROCESSING],
                )
                .order_by("-created_at", "-id")[:1],
            ),
        }

        for label, (index_name, queryset) in querysets.items():
            with self.subTest(query=label):
                plan = self._sqlite_query_plan(queryset)
                self.assertIn(index_name, plan, plan)
