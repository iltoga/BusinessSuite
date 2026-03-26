from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, mock_open, patch

from core.services.invoice_service import create_invoice
from core.utils import formatutils
from customer_applications.models import DocApplication
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from invoices.services.InvoiceService import InvoiceService
from payments.models import Payment
from products.models import Product, ProductCategory

User = get_user_model()


class InvoiceServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="invoice-service-user", password="testpass")
        self.customer = Customer.objects.create(
            customer_type="company",
            company_name="PT Example",
            active=True,
        )
        self.workflow_category = ProductCategory.objects.create(name="Workflow Service", product_type="other")
        self.addon_category = ProductCategory.objects.create(name="Addon Service", product_type="other")
        self.workflow_product = Product.objects.create(
            name="Workflow Visa",
            code="WF-001",
            product_category=self.workflow_category,
            description="Step one\nStep two",
            required_documents="Passport",
            base_price=Decimal("100.00"),
            retail_price=Decimal("100.00"),
        )
        self.addon_product = Product.objects.create(
            name="Addon Service",
            code="ADD-001",
            product_category=self.addon_category,
            description="Add-on line 1\nAdd-on line 2",
            base_price=Decimal("50.00"),
            retail_price=Decimal("50.00"),
        )
        self.doc_application = DocApplication.objects.create(
            customer=self.customer,
            product=self.workflow_product,
            doc_date=date(2026, 3, 1),
            notes="Urgent request\nCustomer asked for fast processing",
            created_by=self.user,
            updated_by=self.user,
        )
        self.invoice = create_invoice(
            data={
                "customer": self.customer,
                "invoice_date": date(2026, 3, 1),
                "due_date": date(2026, 3, 15),
                "sent": True,
                "notes": "Invoice-level notes",
                "invoice_applications": [
                    {
                        "product": self.workflow_product,
                        "customer_application": self.doc_application,
                        "amount": "100.00",
                    },
                    {
                        "product": self.addon_product,
                        "amount": "50.00",
                    },
                ],
            },
            user=self.user,
        )
        self.linked_application = self.invoice.invoice_applications.get(customer_application=self.doc_application)
        self.addon_application = self.invoice.invoice_applications.get(product=self.addon_product)
        self.partial_payment = Payment.objects.create(
            invoice_application=self.linked_application,
            from_customer=self.customer,
            payment_date=date(2026, 3, 4),
            amount=Decimal("40.00"),
            payment_type=Payment.WIRE_TRANSFER,
            created_by=self.user,
            updated_by=self.user,
        )
        self.invoice.refresh_from_db()

    def test_normalize_multiline_text_and_generate_invoice_data(self):
        service = InvoiceService(self.invoice)

        self.assertEqual(
            service._normalize_multiline_text("  First line\r\nSecond line\n\nThird line  "),
            "First line, Second line, Third line",
        )

        data, items = service.generate_invoice_data()

        self.assertEqual(data["customer_name"], "PT Example")
        self.assertEqual(data["customer_company_name"], "")
        self.assertEqual(data["invoice_date"], formatutils.as_date_str(date(2026, 3, 1)))
        self.assertEqual(data["invoice_due_date"], formatutils.as_date_str(date(2026, 3, 15)))
        self.assertEqual(data["total_amount"], formatutils.as_currency(self.invoice.total_amount))
        self.assertEqual(data["total_paid"], formatutils.as_currency(self.invoice.total_paid_amount))
        self.assertEqual(data["total_due"], formatutils.as_currency(self.invoice.total_due_amount))
        self.assertEqual(len(items), 2)

        linked_item = next(item for item in items if item["invoice_item"] == self.workflow_product.code)
        addon_item = next(item for item in items if item["invoice_item"] == self.addon_product.code)

        self.assertEqual(
            linked_item["description"],
            "Step one, Step two - Urgent request, Customer asked for fast processing",
        )
        self.assertEqual(addon_item["description"], "Add-on line 1, Add-on line 2 for PT Example")
        self.assertEqual(linked_item["unit_price"], formatutils.as_currency(self.linked_application.amount))
        self.assertEqual(addon_item["amount"], formatutils.as_currency(self.addon_application.amount))

    def test_generate_partial_invoice_data_includes_payment_rows(self):
        service = InvoiceService(self.invoice)

        data, items, payments = service.generate_partial_invoice_data()

        self.assertEqual(data["total_paid"], formatutils.as_currency(self.invoice.total_paid_amount))
        self.assertEqual(len(items), 2)
        self.assertEqual(len(payments), 1)
        self.assertEqual(
            payments[0],
            {
                "payment_invoice_application": str(self.linked_application.product),
                "payment_date": formatutils.as_date_str(self.partial_payment.payment_date),
                "payment_type": self.partial_payment.get_payment_type_display(),
                "payment_amount": formatutils.as_currency(self.partial_payment.amount),
            },
        )

    @override_settings(
        STATIC_SOURCE_ROOT="/tmp/test-static",
        DOCX_INVOICE_TEMPLATE_NAME="invoice-template.docx",
        DOCX_PARTIAL_INVOICE_TEMPLATE_NAME="partial-template.docx",
    )
    def test_generate_invoice_document_uses_full_template_for_full_invoices(self):
        service = InvoiceService(self.invoice)
        data, items = service.generate_invoice_data()
        doc = MagicMock()
        doc.write.side_effect = lambda buf: buf.write(b"full-doc-output")

        with patch("builtins.open", mock_open()) as open_mock, patch(
            "invoices.services.InvoiceService.MailMerge", return_value=doc
        ):
            buffer = service.generate_invoice_document(data, items)

        self.assertIsInstance(buffer, BytesIO)
        self.assertEqual(buffer.getvalue(), b"full-doc-output")
        open_mock.assert_called_once_with("/tmp/test-static/reporting/invoice-template.docx", "rb")
        doc.merge.assert_called_once_with(**data)
        doc.merge_rows.assert_called_once_with("invoice_item", items)

    @override_settings(
        STATIC_SOURCE_ROOT="/tmp/test-static",
        DOCX_INVOICE_TEMPLATE_NAME="invoice-template.docx",
        DOCX_PARTIAL_INVOICE_TEMPLATE_NAME="partial-template.docx",
    )
    def test_generate_invoice_document_uses_partial_template_and_payment_rows(self):
        service = InvoiceService(self.invoice)
        data, items, payments = service.generate_partial_invoice_data()
        doc = MagicMock()
        doc.write.side_effect = lambda buf: buf.write(b"partial-doc-output")

        with patch("builtins.open", mock_open()) as open_mock, patch(
            "invoices.services.InvoiceService.MailMerge", return_value=doc
        ):
            buffer = service.generate_invoice_document(data, items, payments)

        self.assertIsInstance(buffer, BytesIO)
        self.assertEqual(buffer.getvalue(), b"partial-doc-output")
        open_mock.assert_called_once_with("/tmp/test-static/reporting/partial-template.docx", "rb")
        doc.merge.assert_called_once_with(**data)
        doc.merge_rows.assert_any_call("invoice_item", items)
        doc.merge_rows.assert_any_call("payment_invoice_application", payments)
        self.assertEqual(doc.merge_rows.call_count, 2)

    @override_settings(
        STATIC_SOURCE_ROOT="/tmp/test-static",
        DOCX_INVOICE_TEMPLATE_NAME="missing-branded-template.docx",
    )
    def test_generate_invoice_document_falls_back_when_configured_template_is_missing(self):
        service = InvoiceService(self.invoice)
        data, items = service.generate_invoice_data()
        doc = MagicMock()
        doc.write.side_effect = lambda buf: buf.write(b"fallback-doc-output")

        expected_missing = "/tmp/test-static/reporting/missing-branded-template.docx"
        expected_fallback = "/tmp/test-static/reporting/invoice_template_with_footer_revisbali.docx"

        def open_side_effect(path, mode):
            if path == expected_missing:
                raise FileNotFoundError(path)
            if path == expected_fallback:
                return mock_open(read_data=b"template-bytes")()
            raise AssertionError(f"Unexpected template path: {path}")

        with patch("builtins.open", side_effect=open_side_effect) as open_mock, patch(
            "invoices.services.InvoiceService.MailMerge", return_value=doc
        ):
            buffer = service.generate_invoice_document(data, items)

        self.assertEqual(buffer.getvalue(), b"fallback-doc-output")
        self.assertEqual(open_mock.call_args_list[0].args, (expected_missing, "rb"))
        self.assertEqual(open_mock.call_args_list[1].args, (expected_fallback, "rb"))
        doc.merge.assert_called_once_with(**data)
        doc.merge_rows.assert_called_once_with("invoice_item", items)
