from unittest.mock import patch

from customer_applications.models import DocApplication, Document
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from products.models import DocumentType, Product


class DocumentPreuploadValidationApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="doc_prevalidate_admin",
            email="doc.prevalidate@example.com",
            password="password",
        )
        self.client.force_login(self.user)

        self.customer = Customer.objects.create(customer_type="person", first_name="Pre", last_name="Validate")
        self.product = Product.objects.create(
            name="Prevalidation Product",
            code="PREVALIDATE",
            product_type="visa",
            validation_prompt="Product-specific validation prompt",
        )
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )
        self.document_type = DocumentType.objects.create(
            name="Passport",
            ai_validation=True,
            has_file=True,
            has_doc_number=True,
            has_expiration_date=True,
            validation_rule_ai_positive="Must be a passport bio page",
            validation_rule_ai_negative="No blur and no heavy glare",
        )
        self.document = Document.objects.create(
            doc_application=self.application,
            doc_type=self.document_type,
            created_by=self.user,
            updated_by=self.user,
        )
        self.url = reverse("api-validate-document-category", kwargs={"document_id": self.document.id})

    @patch("api.views_categorization.AIDocumentCategorizer.validate_document")
    def test_validate_document_category_returns_validation_payload(self, validate_document_mock):
        validate_document_mock.return_value = {
            "valid": False,
            "confidence": 0.74,
            "positive_analysis": "Looks like a passport.",
            "negative_issues": ["Image is blurry"],
            "reasoning": "Photo quality is too low for acceptance.",
            "extracted_expiration_date": None,
            "extracted_doc_number": None,
            "extracted_details_markdown": None,
            "ai_provider": "openrouter",
            "ai_provider_name": "OpenRouter",
            "ai_model": "google/gemini-2.5-flash-lite",
        }
        upload = SimpleUploadedFile("passport.pdf", b"%PDF-1.4 fake-pdf", content_type="application/pdf")

        response = self.client.post(self.url, data={"file": upload})

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["validationStatus"], "invalid")
        self.assertFalse(body["matches"])
        self.assertEqual(body["expectedType"], "Passport")
        self.assertEqual(body["detectedType"], "Passport")
        self.assertEqual(body["documentTypeId"], self.document_type.id)
        self.assertEqual(body["confidence"], 0.74)
        self.assertEqual(body["reasoning"], "Photo quality is too low for acceptance.")
        negative_issues = body["validationResult"].get("negativeIssues")
        if negative_issues is None:
            negative_issues = body["validationResult"].get("negative_issues")
        self.assertEqual(negative_issues, ["Image is blurry"])
        self.assertTrue(body["aiValidationEnabled"])
        self.assertEqual(body["validationProvider"], "openrouter")
        self.assertEqual(body["validationProviderName"], "OpenRouter")
        self.assertEqual(body["validationModel"], "google/gemini-2.5-flash-lite")
        self.assertEqual(
            body["validationResult"].get("aiProvider") or body["validationResult"].get("ai_provider"),
            "openrouter",
        )
        self.assertEqual(
            body["validationResult"].get("aiProviderName")
            or body["validationResult"].get("ai_provider_name"),
            "OpenRouter",
        )
        self.assertEqual(
            body["validationResult"].get("aiModel") or body["validationResult"].get("ai_model"),
            "google/gemini-2.5-flash-lite",
        )

        validate_document_mock.assert_called_once_with(
            file_bytes=b"%PDF-1.4 fake-pdf",
            filename="passport.pdf",
            doc_type_name="Passport",
            positive_prompt="Must be a passport bio page",
            negative_prompt="No blur and no heavy glare",
            product_prompt="Product-specific validation prompt",
            require_expiration_date=True,
            require_doc_number=True,
            require_details=False,
        )

    def test_validate_document_category_requires_file(self):
        response = self.client.post(self.url, data={})

        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertEqual(body["code"], "validation_error")
        self.assertIn("file", body["errors"])

    @patch("api.views_categorization.AIDocumentCategorizer.validate_document")
    def test_validate_document_category_hides_provider_error_details(self, validate_document_mock):
        validate_document_mock.side_effect = Exception(
            "OpenRouter API Internal Server Error: Cloudflare 1105 <!DOCTYPE html>..."
        )
        upload = SimpleUploadedFile("passport.pdf", b"%PDF-1.4 fake-pdf", content_type="application/pdf")

        response = self.client.post(self.url, data={"file": upload})

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["validationStatus"], "error")
        self.assertFalse(body["matches"])
        self.assertEqual(body["reasoning"], "AI provider error")
        self.assertEqual(body["validationResult"]["reasoning"], "AI provider error")
        self.assertEqual(body["validationResult"]["negativeIssues"], ["AI provider error"])
        self.assertIsNone(body.get("validationProvider"))
        self.assertIsNone(body.get("validationProviderName"))
        self.assertIsNone(body.get("validationModel"))

    @patch("api.views_categorization.AIDocumentCategorizer.validate_document")
    def test_validate_document_category_error_payload_keeps_runtime_metadata(self, validate_document_mock):
        failure = Exception("OpenRouter timeout")
        setattr(failure, "ai_provider", "openrouter")
        setattr(failure, "ai_provider_name", "OpenRouter")
        setattr(failure, "ai_model", "google/gemini-2.5-flash")
        validate_document_mock.side_effect = failure
        upload = SimpleUploadedFile("passport.pdf", b"%PDF-1.4 fake-pdf", content_type="application/pdf")

        response = self.client.post(self.url, data={"file": upload})

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["validationStatus"], "error")
        self.assertEqual(body["validationProvider"], "openrouter")
        self.assertEqual(body["validationProviderName"], "OpenRouter")
        self.assertEqual(body["validationModel"], "google/gemini-2.5-flash")
        validation_result = body["validationResult"]
        self.assertEqual(validation_result["aiProvider"], "openrouter")
        self.assertEqual(validation_result["aiProviderName"], "OpenRouter")
        self.assertEqual(validation_result["aiModel"], "google/gemini-2.5-flash")
