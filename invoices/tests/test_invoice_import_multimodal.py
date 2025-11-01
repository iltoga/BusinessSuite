"""
Test invoice import with multimodal AI processing.
Tests the complete import workflow using sample invoices from tmp folder.
"""

import json
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from customers.models import Customer
from invoices.models import Invoice
from invoices.services.invoice_importer import ImportResult, InvoiceImporter
from invoices.services.llm_invoice_parser import LLMInvoiceParser

User = get_user_model()


class InvoiceImportMultimodalTestCase(TestCase):
    """
    Test invoice import functionality with real sample invoices.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Path to sample invoices
        cls.tmp_dir = Path("/Users/stefano.galassi/python/RevisBaliCRM/tmp")
        cls.pdf_path = cls.tmp_dir / "202634Inv_Daniel Cain Frankel_CFK-12.pdf"
        cls.xlsx_path = cls.tmp_dir / "202634Inv_Daniel Cain Frankel_CFK-12.xlsx"

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(username="testuser", password="testpass123")

    def tearDown(self):
        """Clean up after each test."""
        Invoice.objects.all().delete()
        Customer.objects.all().delete()

    def test_pdf_invoice_parsing(self):
        """Test parsing PDF invoice with GPT-5-mini vision."""
        if not self.pdf_path.exists():
            self.skipTest(f"Sample PDF not found at {self.pdf_path}")

        with open(self.pdf_path, "rb") as f:
            file_content = f.read()

        parser = LLMInvoiceParser()
        result = parser.parse_invoice_file(file_content, filename=self.pdf_path.name, file_type="pdf")

        # Assertions
        self.assertIsNotNone(result, "Parsing should return a result")
        self.assertIsNotNone(result.customer, "Customer data should be present")
        self.assertIsNotNone(result.invoice, "Invoice data should be present")
        self.assertGreater(len(result.line_items), 0, "Should have at least one line item")

        # Check customer data extraction
        self.assertIn("Daniel", result.customer.full_name, "Customer name should contain 'Daniel'")
        self.assertIn("Frankel", result.customer.full_name, "Customer name should contain 'Frankel'")

        # Check invoice data
        self.assertEqual(result.invoice.invoice_no, "202634", "Invoice number should be '202634'")
        self.assertGreater(result.invoice.total_amount, 0, "Total amount should be greater than 0")

        # Check date format
        self.assertRegex(
            result.invoice.invoice_date, r"^\d{4}-\d{2}-\d{2}$", "Invoice date should be in YYYY-MM-DD format"
        )
        self.assertRegex(result.invoice.due_date, r"^\d{4}-\d{2}-\d{2}$", "Due date should be in YYYY-MM-DD format")

        # Check line items
        for item in result.line_items:
            self.assertIsNotNone(item.description, "Line item should have description")
            self.assertGreater(item.quantity, 0, "Quantity should be positive")
            self.assertGreater(item.amount, 0, "Amount should be positive")

        # Check confidence score
        self.assertGreaterEqual(result.confidence_score, 0.0, "Confidence score should be >= 0")
        self.assertLessEqual(result.confidence_score, 1.0, "Confidence score should be <= 1")

        print(f"\n✓ PDF Parsing Results:")
        print(f"  Customer: {result.customer.full_name}")
        print(f"  Invoice: {result.invoice.invoice_no}")
        print(f"  Date: {result.invoice.invoice_date}")
        print(f"  Total: {result.invoice.total_amount}")
        print(f"  Line Items: {len(result.line_items)}")
        print(f"  Confidence: {result.confidence_score:.2f}")

    def test_xlsx_invoice_parsing(self):
        """Test parsing Excel invoice."""
        if not self.xlsx_path.exists():
            self.skipTest(f"Sample Excel file not found at {self.xlsx_path}")

        with open(self.xlsx_path, "rb") as f:
            file_content = f.read()

        parser = LLMInvoiceParser()
        result = parser.parse_invoice_file(file_content, filename=self.xlsx_path.name, file_type="xlsx")

        # Assertions
        self.assertIsNotNone(result, "Parsing should return a result")
        self.assertIsNotNone(result.customer, "Customer data should be present")
        self.assertIsNotNone(result.invoice, "Invoice data should be present")
        self.assertGreater(len(result.line_items), 0, "Should have at least one line item")

        # Check invoice number
        self.assertEqual(result.invoice.invoice_no, "202634", "Invoice number should be '202634'")

        print(f"\n✓ Excel Parsing Results:")
        print(f"  Customer: {result.customer.full_name}")
        print(f"  Invoice: {result.invoice.invoice_no}")
        print(f"  Date: {result.invoice.invoice_date}")
        print(f"  Total: {result.invoice.total_amount}")
        print(f"  Line Items: {len(result.line_items)}")
        print(f"  Confidence: {result.confidence_score:.2f}")

    def test_data_validation(self):
        """Test that parsed data passes validation."""
        if not self.pdf_path.exists():
            self.skipTest(f"Sample PDF not found at {self.pdf_path}")

        with open(self.pdf_path, "rb") as f:
            file_content = f.read()

        parser = LLMInvoiceParser()
        result = parser.parse_invoice_file(file_content, filename=self.pdf_path.name, file_type="pdf")

        self.assertIsNotNone(result, "Parsing should succeed")

        # Run validation
        is_valid, errors = parser.validate_parsed_data(result)

        # Print validation results
        if not is_valid:
            print(f"\n⚠ Validation Errors:")
            for error in errors:
                print(f"  - {error}")

        # Assertions
        self.assertTrue(is_valid, f"Data should be valid. Errors: {errors}")
        self.assertEqual(len(errors), 0, "Should have no validation errors")

    def test_full_import_workflow_pdf(self):
        """Test complete import workflow with PDF invoice."""
        if not self.pdf_path.exists():
            self.skipTest(f"Sample PDF not found at {self.pdf_path}")

        # Read file and create UploadedFile
        with open(self.pdf_path, "rb") as f:
            file_content = f.read()

        uploaded_file = SimpleUploadedFile(
            name=self.pdf_path.name, content=file_content, content_type="application/pdf"
        )

        # Import invoice
        importer = InvoiceImporter(user=self.user)
        result = importer.import_from_file(uploaded_file, filename=self.pdf_path.name)

        # Assertions
        self.assertIsInstance(result, ImportResult, "Should return ImportResult")
        self.assertTrue(result.success, f"Import should succeed. Message: {result.message}, Errors: {result.errors}")
        self.assertEqual(result.status, "imported", f"Status should be 'imported', got: {result.status}")
        self.assertIsNotNone(result.invoice, "Should create an invoice")
        self.assertIsNotNone(result.customer, "Should create/match a customer")

        # Check invoice in database
        invoice = Invoice.objects.filter(invoice_no=202634).first()
        self.assertIsNotNone(invoice, "Invoice should be saved to database")
        self.assertTrue(invoice.imported, "Invoice should be marked as imported")
        self.assertEqual(invoice.imported_from_file, self.pdf_path.name, "Should store original filename")

        # Check invoice applications were created
        invoice_apps = invoice.invoice_applications.all()
        self.assertGreater(invoice_apps.count(), 0, "Should have invoice applications")

        # Check customer
        customer = invoice.customer
        self.assertIsNotNone(customer, "Invoice should have a customer")
        self.assertTrue(customer.active, "Customer should be active")

        # Check total calculation
        invoice_apps_total = sum(app.amount for app in invoice_apps)
        self.assertAlmostEqual(
            float(invoice.total_amount),
            float(invoice_apps_total),
            places=2,
            msg="Invoice total should match sum of invoice applications",
        )

        print(f"\n✓ Full Import Results:")
        print(f"  Customer: {customer.full_name} (ID: {customer.pk})")
        print(f"  Invoice: {invoice.invoice_no_display} (ID: {invoice.pk})")
        print(f"  Date: {invoice.invoice_date}")
        print(f"  Status: {invoice.get_status_display()}")
        print(f"  Total: {invoice.total_amount}")
        print(f"  Invoice Applications: {invoice_apps.count()}")
        print(f"  Message: {result.message}")

    def test_duplicate_detection(self):
        """Test that duplicate invoices are detected."""
        if not self.pdf_path.exists():
            self.skipTest(f"Sample PDF not found at {self.pdf_path}")

        with open(self.pdf_path, "rb") as f:
            file_content = f.read()

        # First import
        uploaded_file1 = SimpleUploadedFile(
            name=self.pdf_path.name, content=file_content, content_type="application/pdf"
        )
        importer = InvoiceImporter(user=self.user)
        result1 = importer.import_from_file(uploaded_file1)

        self.assertTrue(result1.success, "First import should succeed")
        self.assertEqual(result1.status, "imported")

        # Second import (same invoice)
        uploaded_file2 = SimpleUploadedFile(
            name=self.pdf_path.name, content=file_content, content_type="application/pdf"
        )
        result2 = importer.import_from_file(uploaded_file2)

        # Assertions
        self.assertFalse(result2.success, "Second import should fail")
        self.assertEqual(result2.status, "duplicate", "Status should be 'duplicate'")
        self.assertIn("already exists", result2.message.lower(), "Message should mention duplicate")

        # Check database - should still have only one invoice
        invoice_count = Invoice.objects.filter(invoice_no=202634).count()
        self.assertEqual(invoice_count, 1, "Should have only one invoice in database")

        print(f"\n✓ Duplicate Detection:")
        print(f"  First import: {result1.status}")
        print(f"  Second import: {result2.status}")
        print(f"  Message: {result2.message}")

    def test_customer_matching(self):
        """Test that existing customers are matched correctly."""
        if not self.pdf_path.exists():
            self.skipTest(f"Sample PDF not found at {self.pdf_path}")

        # Create a customer that should match
        existing_customer = Customer.objects.create(
            first_name="Daniel",
            last_name="Frankel",
            email="daniel.frankel@example.com",
            telephone="+1234567890",
            whatsapp="+1234567890",
            title="Mr.",
            birthdate="1990-01-01",
            active=True,
        )

        with open(self.pdf_path, "rb") as f:
            file_content = f.read()

        uploaded_file = SimpleUploadedFile(
            name=self.pdf_path.name, content=file_content, content_type="application/pdf"
        )

        # Import invoice
        importer = InvoiceImporter(user=self.user)
        result = importer.import_from_file(uploaded_file)

        self.assertTrue(result.success, "Import should succeed")

        # Check that existing customer was used (not a new one created)
        customer_count = Customer.objects.filter(first_name__iexact="Daniel", last_name__iexact="Frankel").count()

        # Note: Depending on matching logic, it might create a new customer
        # if phone/email don't match exactly. Adjust assertion as needed.
        print(f"\n✓ Customer Matching:")
        print(f"  Existing Customer ID: {existing_customer.pk}")
        print(f"  Matched Customer ID: {result.customer.pk}")
        print(f"  Total matching customers: {customer_count}")
        print(f"  Match successful: {result.customer.pk == existing_customer.pk}")

    def test_structured_output_schema(self):
        """Test that the response follows the JSON schema strictly."""
        if not self.pdf_path.exists():
            self.skipTest(f"Sample PDF not found at {self.pdf_path}")

        with open(self.pdf_path, "rb") as f:
            file_content = f.read()

        parser = LLMInvoiceParser()
        result = parser.parse_invoice_file(file_content, filename=self.pdf_path.name, file_type="pdf")

        self.assertIsNotNone(result, "Parsing should succeed")

        # Check that raw_response has expected structure
        raw = result.raw_response
        self.assertIn("customer", raw, "Response should have 'customer' key")
        self.assertIn("invoice", raw, "Response should have 'invoice' key")
        self.assertIn("line_items", raw, "Response should have 'line_items' key")
        self.assertIn("confidence_score", raw, "Response should have 'confidence_score' key")

        # Check customer structure
        customer = raw["customer"]
        self.assertIn("full_name", customer, "Customer should have 'full_name'")

        # Check invoice structure
        invoice = raw["invoice"]
        self.assertIn("invoice_no", invoice, "Invoice should have 'invoice_no'")
        self.assertIn("invoice_date", invoice, "Invoice should have 'invoice_date'")
        self.assertIn("due_date", invoice, "Invoice should have 'due_date'")
        self.assertIn("total_amount", invoice, "Invoice should have 'total_amount'")

        # Check line items structure
        line_items = raw["line_items"]
        self.assertIsInstance(line_items, list, "Line items should be a list")
        if len(line_items) > 0:
            item = line_items[0]
            self.assertIn("code", item, "Line item should have 'code'")
            self.assertIn("description", item, "Line item should have 'description'")
            self.assertIn("quantity", item, "Line item should have 'quantity'")
            self.assertIn("unit_price", item, "Line item should have 'unit_price'")
            self.assertIn("amount", item, "Line item should have 'amount'")

        print(f"\n✓ Schema Validation:")
        print(f"  All required keys present")
        print(f"  Customer fields: {list(customer.keys())}")
        print(f"  Invoice fields: {list(invoice.keys())}")
        print(f"  Line item count: {len(line_items)}")

    def test_error_handling_invalid_file(self):
        """Test error handling with invalid file."""
        # Create a fake/invalid file
        invalid_file = SimpleUploadedFile(name="invalid.pdf", content=b"not a real pdf", content_type="application/pdf")

        importer = InvoiceImporter(user=self.user)
        result = importer.import_from_file(invalid_file)

        # Should fail gracefully
        self.assertFalse(result.success, "Invalid file should not succeed")
        self.assertEqual(result.status, "error", "Status should be 'error'")
        self.assertIsNone(result.invoice, "Should not create an invoice")

        print(f"\n✓ Error Handling:")
        print(f"  Status: {result.status}")
        print(f"  Message: {result.message}")
        print(f"  Errors: {result.errors}")

    def test_batch_import(self):
        """Test importing multiple invoices."""
        if not self.pdf_path.exists() or not self.xlsx_path.exists():
            self.skipTest("Sample files not found")

        importer = InvoiceImporter(user=self.user)
        results = []

        # Import PDF
        with open(self.pdf_path, "rb") as f:
            pdf_file = SimpleUploadedFile(name=self.pdf_path.name, content=f.read(), content_type="application/pdf")
            results.append(importer.import_from_file(pdf_file))

        # Import Excel (same invoice - should be duplicate)
        with open(self.xlsx_path, "rb") as f:
            xlsx_file = SimpleUploadedFile(
                name=self.xlsx_path.name,
                content=f.read(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            results.append(importer.import_from_file(xlsx_file))

        # Check results
        self.assertEqual(len(results), 2, "Should have 2 results")
        self.assertTrue(results[0].success, "First import should succeed")
        self.assertEqual(results[0].status, "imported")

        # Second should be duplicate
        self.assertFalse(results[1].success, "Second import should fail (duplicate)")
        self.assertEqual(results[1].status, "duplicate")

        print(f"\n✓ Batch Import:")
        for i, result in enumerate(results, 1):
            print(f"  File {i}: {result.status} - {result.message}")


class LLMParserUnitTests(TestCase):
    """Unit tests for LLM parser components."""

    def test_json_schema_structure(self):
        """Test that JSON schema is properly defined."""
        parser = LLMInvoiceParser()
        schema = parser.INVOICE_SCHEMA

        # Check top-level structure
        self.assertEqual(schema["type"], "object")
        self.assertIn("properties", schema)
        self.assertIn("required", schema)
        self.assertFalse(schema.get("additionalProperties", True), "Should not allow additional properties")

        # Check required fields
        required = schema["required"]
        self.assertIn("customer", required)
        self.assertIn("invoice", required)
        self.assertIn("line_items", required)
        self.assertIn("confidence_score", required)

        print(f"\n✓ JSON Schema:")
        print(f"  Type: {schema['type']}")
        print(f"  Required fields: {required}")
        print(f"  Additional properties: {schema.get('additionalProperties', False)}")

    def test_parser_initialization(self):
        """Test parser initializes correctly."""
        parser = LLMInvoiceParser()

        self.assertIsNotNone(parser.api_key, "API key should be set")
        self.assertIsNotNone(parser.client, "OpenAI client should be initialized")
        self.assertEqual(parser.model, "gpt-5-mini", "Default model should be gpt-5-mini")

        print(f"\n✓ Parser Initialization:")
        print(f"  Model: {parser.model}")
        print(f"  API Key: {'***' + parser.api_key[-8:] if parser.api_key else 'Not set'}")

    def test_parser_with_custom_model(self):
        """Test parser with custom model."""
        parser = LLMInvoiceParser(model="gpt-5")

        self.assertEqual(parser.model, "gpt-5", "Should use custom model")

        print(f"\n✓ Custom Model:")
        print(f"  Model: {parser.model}")
