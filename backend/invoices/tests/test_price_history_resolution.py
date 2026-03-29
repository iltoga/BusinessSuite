"""Tests for invoice price history resolution logic."""

from datetime import date, datetime
from decimal import Decimal

from core.services.invoice_service import create_invoice
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from products.models import Product, ProductPriceHistory

User = get_user_model()


class ProductPriceHistoryResolutionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="history-user", password="testpass")
        self.customer = Customer.objects.create(customer_type="person", first_name="Alice", last_name="History")
        self.product = Product.objects.create(
            name="History Product",
            code="HIST-1",
            product_type="other",
            base_price=Decimal("100.00"),
            retail_price=Decimal("150.00"),
        )

    def test_resolve_for_invoice_date_prefers_matching_or_closest_prior_history(self):
        ProductPriceHistory.objects.filter(product=self.product).delete()
        first = ProductPriceHistory.objects.create(
            product=self.product,
            base_price=Decimal("80.00"),
            retail_price=Decimal("120.00"),
            currency="IDR",
            effective_from=timezone.make_aware(datetime(2026, 1, 1, 0, 0, 0)),
            effective_to=timezone.make_aware(datetime(2026, 2, 1, 0, 0, 0)),
        )
        second = ProductPriceHistory.objects.create(
            product=self.product,
            base_price=Decimal("90.00"),
            retail_price=Decimal("140.00"),
            currency="IDR",
            effective_from=timezone.make_aware(datetime(2026, 2, 1, 0, 0, 0)),
        )

        matching = ProductPriceHistory.resolve_for_invoice_date(
            product_id=self.product.id,
            invoice_date=date(2026, 1, 15),
        )
        self.assertEqual(matching.id, first.id)

        later = ProductPriceHistory.resolve_for_invoice_date(
            product_id=self.product.id,
            invoice_date=date(2026, 3, 15),
        )
        self.assertEqual(later.id, second.id)

        before_first = ProductPriceHistory.resolve_for_invoice_date(
            product_id=self.product.id,
            invoice_date=date(2025, 12, 15),
        )
        self.assertEqual(before_first.id, first.id)

    def test_create_invoice_does_not_synthesize_price_history_when_none_exists(self):
        ProductPriceHistory.objects.filter(product=self.product).delete()

        invoice = create_invoice(
            data={
                "customer": self.customer,
                "invoice_date": date(2026, 3, 10),
                "due_date": date(2026, 3, 10),
                "notes": "No synthetic history please",
                "sent": False,
                "invoice_applications": [
                    {
                        "product": self.product,
                        "amount": "150.00",
                    }
                ],
            },
            user=self.user,
        )

        invoice_line = invoice.invoice_applications.get()
        self.assertIsNone(invoice_line.price_history_id)
        self.assertFalse(ProductPriceHistory.objects.filter(product=self.product).exists())
