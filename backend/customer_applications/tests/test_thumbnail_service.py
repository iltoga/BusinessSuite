"""Tests for the document thumbnail service."""

from datetime import date
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from customer_applications.models import DocApplication, Document
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from products.models import DocumentType, Product

User = get_user_model()


class DocumentThumbnailServiceIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("thumb_admin", "thumb_admin@example.com", "pass")
        self.customer = Customer.objects.create(first_name="Thumb", last_name="User")
        self.product = Product.objects.create(name="Thumb Product", code="THUMB-1")
        self.doc_type = DocumentType.objects.create(name="Thumb Passport", has_file=True)

    @staticmethod
    def _build_image_upload(name: str = "passport.png") -> SimpleUploadedFile:
        image = Image.new("RGB", (1200, 800), "#3455aa")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def _create_application(self):
        return DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 3, 2),
            created_by=self.user,
        )

    def test_image_upload_generates_thumbnail_and_cached_url(self):
        application = self._create_application()
        with TemporaryDirectory() as media_root:
            with self.settings(
                MEDIA_ROOT=media_root,
                STORAGES={
                    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
                },
            ):
                document = Document.objects.create(
                    doc_application=application,
                    doc_type=self.doc_type,
                    file=self._build_image_upload(),
                    required=True,
                    created_by=self.user,
                )
                document.refresh_from_db()

                self.assertTrue(document.thumbnail.name.endswith(".jpg"))
                self.assertIn("/thumbnails/document_", document.thumbnail.name)
                self.assertTrue(document.thumbnail_link)
                self.assertTrue(default_storage.exists(document.thumbnail.name))

    def test_clearing_file_removes_thumbnail(self):
        application = self._create_application()
        with TemporaryDirectory() as media_root:
            with self.settings(
                MEDIA_ROOT=media_root,
                STORAGES={
                    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
                },
            ):
                document = Document.objects.create(
                    doc_application=application,
                    doc_type=self.doc_type,
                    file=self._build_image_upload(),
                    required=True,
                    created_by=self.user,
                )
                document.refresh_from_db()
                thumbnail_path = document.thumbnail.name
                self.assertTrue(default_storage.exists(thumbnail_path))

                document.file = ""
                document.save()
                document.refresh_from_db()

                self.assertEqual(document.thumbnail.name, "")
                self.assertEqual(document.thumbnail_link, "")
                self.assertFalse(default_storage.exists(thumbnail_path))

    @patch("customer_applications.services.thumbnail_service.convert_from_bytes")
    def test_pdf_upload_generates_thumbnail_via_pdf2image(self, convert_from_bytes_mock):
        convert_from_bytes_mock.return_value = [Image.new("RGB", (900, 1200), "#ffffff")]
        application = self._create_application()

        with TemporaryDirectory() as media_root:
            with self.settings(
                MEDIA_ROOT=media_root,
                STORAGES={
                    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
                },
            ):
                pdf_upload = SimpleUploadedFile(
                    "passport.pdf",
                    b"%PDF-1.4\n%fake\n",
                    content_type="application/pdf",
                )
                document = Document.objects.create(
                    doc_application=application,
                    doc_type=self.doc_type,
                    file=pdf_upload,
                    required=True,
                    created_by=self.user,
                )
                document.refresh_from_db()

                convert_from_bytes_mock.assert_called_once()
                self.assertTrue(document.thumbnail.name.endswith(".jpg"))
                self.assertTrue(default_storage.exists(document.thumbnail.name))
