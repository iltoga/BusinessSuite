import os
from datetime import date
from io import BytesIO
from unittest.mock import Mock, PropertyMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from customer_applications.hooks.surat_permohonan import SuratPermohonanHook
from customer_applications.models import DocApplication, Document
from customers.models import Customer
from products.models import DocumentType, Product

User = get_user_model()


class SuratPermohonanHookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("surat-admin", "suratadmin@example.com", "pass")
        self.customer = Customer.objects.create(
            first_name="Surat",
            last_name="Tester",
            address_bali="Denpasar, Bali",
        )
        self.product = Product.objects.create(name="Test Product", code="SURAT-HOOK-1", required_documents="")
        self.doc_type = DocumentType.objects.create(name="Surat Permohonan dan Jaminan", has_file=True)
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 2, 24),
            created_by=self.user,
        )
        self.document = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type,
            required=True,
            created_by=self.user,
        )

    def test_auto_generate_succeeds_when_storage_has_no_path_support(self):
        hook = SuratPermohonanHook()

        with (
            patch(
                "letters.services.LetterService.LetterService.generate_letter_data",
                return_value={"customer_name": self.customer.full_name},
            ),
            patch(
                "letters.services.LetterService.LetterService.generate_letter_document",
                return_value=BytesIO(b"docx-content"),
            ),
            patch(
                "customer_applications.hooks.surat_permohonan.PDFConverter.docx_buffer_to_pdf",
                return_value=b"%PDF-1.4\n",
            ),
            patch(
                "django.db.models.fields.files.FieldFile.path",
                new_callable=PropertyMock,
                side_effect=NotImplementedError("This backend doesn't support absolute paths."),
            ),
        ):
            result = hook.execute_action("auto_generate", self.document, Mock())

        self.assertTrue(result["success"])
        self.document.refresh_from_db()
        stored_filename = os.path.basename(self.document.file.name)
        self.assertTrue(stored_filename.startswith("Surat_Permohonan_dan_Jaminan"))
        self.assertTrue(stored_filename.endswith(".pdf"))
