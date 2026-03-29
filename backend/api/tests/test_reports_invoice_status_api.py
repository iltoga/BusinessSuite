"""Regression tests for invoice status report API behavior."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from customers.models import Customer
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.db.models import Sum
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from invoices.models import Invoice, InvoiceApplication
from payments.models import Payment
from products.models import Product
from reports.services import build_invoice_status_dashboard_context
from reports.utils import format_currency
from rest_framework.test import APIClient

User = get_user_model()


class InvoiceStatusDashboardApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("manager-reports", "manager-reports@example.com", "pass")
        manager_group, _ = Group.objects.get_or_create(name="manager")
        self.user.groups.add(manager_group)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.customer = Customer.objects.create(first_name="Ada", last_name="Report")
        self.product = Product.objects.create(name="Visa Service", code="VISA-SVC", product_type="visa")
        self.today = timezone.localdate()

    def _store_invoice(self, *, status: str, total_amount: Decimal, due_days_ago: int, sent: bool = True) -> Invoice:
        invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=self.today - timedelta(days=max(due_days_ago, 1) + 10),
            due_date=self.today - timedelta(days=due_days_ago),
            sent=sent,
            created_by=self.user,
            updated_by=self.user,
        )
        Invoice.objects.filter(pk=invoice.pk).update(total_amount=total_amount, status=status, sent=sent)
        invoice.refresh_from_db()
        return invoice

    def _create_paid_invoice(
        self, *, total_amount: Decimal, invoice_days_ago: int, payment_days_after_invoice: int
    ) -> Invoice:
        invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=self.today - timedelta(days=invoice_days_ago),
            due_date=self.today - timedelta(days=max(invoice_days_ago - 3, 0)),
            sent=True,
            created_by=self.user,
            updated_by=self.user,
        )
        invoice_application = InvoiceApplication.objects.create(
            invoice=invoice,
            product=self.product,
            amount=total_amount,
        )
        Payment.objects.create(
            invoice_application=invoice_application,
            from_customer=self.customer,
            payment_date=invoice.invoice_date + timedelta(days=payment_days_after_invoice),
            amount=total_amount,
            created_by=self.user,
            updated_by=self.user,
        )
        invoice.refresh_from_db()
        return invoice

    def _legacy_context(self) -> dict:
        status_data = []
        for status_code, status_label in Invoice.INVOICE_STATUS_CHOICES:
            invoices = Invoice.objects.filter(status=status_code)
            count = invoices.count()
            total = invoices.aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
            status_data.append(
                {
                    "status": status_label,
                    "code": status_code,
                    "count": count,
                    "total": float(total),
                    "total_formatted": format_currency(total),
                }
            )

        aging_buckets = [
            {"label": "0-30 days", "min": 0, "max": 30},
            {"label": "31-60 days", "min": 31, "max": 60},
            {"label": "61-90 days", "min": 61, "max": 90},
            {"label": "90+ days", "min": 91, "max": None},
        ]

        aging_data = []
        for bucket in aging_buckets:
            end_date = self.today - timedelta(days=bucket["min"])
            if bucket["max"] is not None:
                start_date = self.today - timedelta(days=bucket["max"])
                invoices = Invoice.objects.filter(
                    due_date__gte=start_date,
                    due_date__lte=end_date,
                    status__in=[Invoice.PENDING_PAYMENT, Invoice.PARTIAL_PAYMENT, Invoice.OVERDUE],
                )
            else:
                invoices = Invoice.objects.filter(
                    due_date__lte=end_date,
                    status__in=[Invoice.PENDING_PAYMENT, Invoice.PARTIAL_PAYMENT, Invoice.OVERDUE],
                )
            outstanding = Decimal("0")
            for invoice in invoices:
                outstanding += invoice.total_due_amount
            aging_data.append(
                {
                    "label": bucket["label"],
                    "count": invoices.count(),
                    "total": float(outstanding),
                    "total_formatted": format_currency(outstanding),
                }
            )

        total_days = 0
        count_with_payment = 0
        for invoice in Invoice.objects.filter(status=Invoice.PAID):
            first_payment = invoice.invoice_applications.first()
            if first_payment and first_payment.payments.exists():
                payment_date = first_payment.payments.order_by("payment_date").first().payment_date
                total_days += (payment_date - invoice.invoice_date).days
                count_with_payment += 1

        paid_count = Invoice.objects.filter(status=Invoice.PAID).count()
        total_count = Invoice.objects.count()
        return {
            "status_data": status_data,
            "aging_data": aging_data,
            "avg_days_to_payment": round(total_days / count_with_payment if count_with_payment else 0, 1),
            "collection_rate": round((paid_count / total_count * 100) if total_count else 0, 1),
        }

    def test_service_matches_legacy_invoice_status_semantics(self):
        self._store_invoice(status=Invoice.PENDING_PAYMENT, total_amount=Decimal("100.00"), due_days_ago=10)
        self._store_invoice(status=Invoice.PARTIAL_PAYMENT, total_amount=Decimal("250.00"), due_days_ago=45)
        self._store_invoice(status=Invoice.OVERDUE, total_amount=Decimal("400.00"), due_days_ago=75)
        self._store_invoice(status=Invoice.OVERDUE, total_amount=Decimal("500.00"), due_days_ago=120)
        self._store_invoice(status=Invoice.CREATED, total_amount=Decimal("50.00"), due_days_ago=2, sent=False)
        self._create_paid_invoice(total_amount=Decimal("300.00"), invoice_days_ago=20, payment_days_after_invoice=5)

        expected = self._legacy_context()
        actual = build_invoice_status_dashboard_context(as_of_date=self.today)

        self.assertEqual(actual, expected)

    def test_service_reduces_query_count_vs_legacy_implementation(self):
        self._store_invoice(status=Invoice.PENDING_PAYMENT, total_amount=Decimal("100.00"), due_days_ago=5)
        self._store_invoice(status=Invoice.PARTIAL_PAYMENT, total_amount=Decimal("200.00"), due_days_ago=35)
        self._store_invoice(status=Invoice.OVERDUE, total_amount=Decimal("300.00"), due_days_ago=65)
        self._store_invoice(status=Invoice.OVERDUE, total_amount=Decimal("400.00"), due_days_ago=120)
        self._create_paid_invoice(total_amount=Decimal("500.00"), invoice_days_ago=40, payment_days_after_invoice=7)
        self._create_paid_invoice(total_amount=Decimal("600.00"), invoice_days_ago=15, payment_days_after_invoice=2)

        with CaptureQueriesContext(connection) as legacy_queries:
            self._legacy_context()

        with CaptureQueriesContext(connection) as optimized_queries:
            build_invoice_status_dashboard_context(as_of_date=self.today)

        self.assertGreater(len(legacy_queries), len(optimized_queries))
        self.assertLessEqual(len(optimized_queries), 4)

    def test_invoice_status_api_uses_service_not_template_view(self):
        self._store_invoice(status=Invoice.PENDING_PAYMENT, total_amount=Decimal("125.00"), due_days_ago=10)
        expected = build_invoice_status_dashboard_context(as_of_date=self.today)

        with patch(
            "reports.views.invoice_status_dashboard_view.InvoiceStatusDashboardView.get_context_data",
            side_effect=AssertionError("API should not call template view context building"),
        ), patch("api.reports_views.build_invoice_status_dashboard_context", return_value=expected) as service_mock:
            response = self.client.get(reverse("api-report-invoice-status"))

        self.assertEqual(response.status_code, 200)
        service_mock.assert_called_once_with()
        self.assertEqual(response.data, expected)
