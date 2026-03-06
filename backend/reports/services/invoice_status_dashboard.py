from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Case, CharField, Count, DecimalField, F, OuterRef, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from invoices.models import Invoice, InvoiceApplication
from payments.models import Payment
from reports.utils import format_currency

DECIMAL_FIELD = DecimalField(max_digits=12, decimal_places=2)
DECIMAL_ZERO = Value(Decimal("0.00"), output_field=DECIMAL_FIELD)
AGING_BUCKETS = [
    {"label": "0-30 days", "min": 0, "max": 30},
    {"label": "31-60 days", "min": 31, "max": 60},
    {"label": "61-90 days", "min": 61, "max": 90},
    {"label": "90+ days", "min": 91, "max": None},
]
UNPAID_STATUSES = [Invoice.PENDING_PAYMENT, Invoice.PARTIAL_PAYMENT, Invoice.OVERDUE]


def _with_invoice_payment_totals(queryset):
    payment_total_subquery = (
        Payment.objects.filter(invoice_application__invoice=OuterRef("pk"))
        .values("invoice_application__invoice")
        .annotate(total_paid=Coalesce(Sum("amount"), DECIMAL_ZERO))
        .values("total_paid")[:1]
    )

    return queryset.annotate(
        annotated_total_paid=Coalesce(
            Subquery(payment_total_subquery, output_field=DECIMAL_FIELD),
            DECIMAL_ZERO,
        )
    ).annotate(
        annotated_total_due=Coalesce(F("total_amount"), DECIMAL_ZERO)
        - Coalesce(F("annotated_total_paid"), DECIMAL_ZERO)
    )


def _build_status_data() -> list[dict[str, Any]]:
    status_rows = {
        row["status"]: row
        for row in (
            Invoice.objects.values("status")
            .annotate(
                count=Count("pk"),
                total=Coalesce(Sum("total_amount"), DECIMAL_ZERO),
            )
            .order_by()
        )
    }

    status_data: list[dict[str, Any]] = []
    for status_code, status_label in Invoice.INVOICE_STATUS_CHOICES:
        row = status_rows.get(status_code, {})
        total = row.get("total") or Decimal("0.00")
        status_data.append(
            {
                "status": status_label,
                "code": status_code,
                "count": int(row.get("count") or 0),
                "total": float(total),
                "total_formatted": format_currency(total),
            }
        )
    return status_data


def _build_aging_data(as_of_date: date) -> list[dict[str, Any]]:
    bucket_rows = {
        row["aging_bucket"]: row
        for row in (
            _with_invoice_payment_totals(Invoice.objects.filter(status__in=UNPAID_STATUSES))
            .annotate(
                aging_bucket=Case(
                    When(
                        due_date__gte=as_of_date - timedelta(days=30),
                        due_date__lte=as_of_date,
                        then=Value("0-30 days"),
                    ),
                    When(
                        due_date__gte=as_of_date - timedelta(days=60),
                        due_date__lte=as_of_date - timedelta(days=31),
                        then=Value("31-60 days"),
                    ),
                    When(
                        due_date__gte=as_of_date - timedelta(days=90),
                        due_date__lte=as_of_date - timedelta(days=61),
                        then=Value("61-90 days"),
                    ),
                    When(due_date__lte=as_of_date - timedelta(days=91), then=Value("90+ days")),
                    default=Value(None),
                    output_field=CharField(),
                )
            )
            .exclude(aging_bucket__isnull=True)
            .values("aging_bucket")
            .annotate(
                count=Count("pk"),
                total=Coalesce(Sum("annotated_total_due"), DECIMAL_ZERO),
            )
            .order_by()
        )
    }

    aging_data: list[dict[str, Any]] = []
    for bucket in AGING_BUCKETS:
        row = bucket_rows.get(bucket["label"], {})
        total = row.get("total") or Decimal("0.00")
        aging_data.append(
            {
                "label": bucket["label"],
                "count": int(row.get("count") or 0),
                "total": float(total),
                "total_formatted": format_currency(total),
            }
        )
    return aging_data


def _compute_avg_days_to_payment() -> float:
    latest_invoice_application_subquery = (
        InvoiceApplication.objects.filter(invoice=OuterRef("pk")).order_by("-id").values("pk")[:1]
    )
    paid_invoices = list(
        Invoice.objects.filter(status=Invoice.PAID)
        .annotate(latest_invoice_application_id=Subquery(latest_invoice_application_subquery))
        .exclude(latest_invoice_application_id__isnull=True)
        .values("invoice_date", "latest_invoice_application_id")
    )
    if not paid_invoices:
        return 0.0

    first_payments_by_application: dict[int, date] = {}
    for invoice_application_id, payment_date in (
        Payment.objects.filter(
            invoice_application_id__in=[row["latest_invoice_application_id"] for row in paid_invoices]
        )
        .order_by("invoice_application_id", "payment_date")
        .values_list("invoice_application_id", "payment_date")
    ):
        first_payments_by_application.setdefault(invoice_application_id, payment_date)

    total_days = 0
    count_with_payment = 0
    for row in paid_invoices:
        payment_date = first_payments_by_application.get(row["latest_invoice_application_id"])
        if payment_date is None:
            continue
        total_days += (payment_date - row["invoice_date"]).days
        count_with_payment += 1

    if count_with_payment == 0:
        return 0.0
    return round(total_days / count_with_payment, 1)


def build_invoice_status_dashboard_context(*, as_of_date: date | None = None) -> dict[str, Any]:
    today = as_of_date or timezone.localdate()
    status_data = _build_status_data()
    total_count = sum(row["count"] for row in status_data)
    paid_count = next((row["count"] for row in status_data if row["code"] == Invoice.PAID), 0)
    collection_rate = round((paid_count / total_count * 100) if total_count else 0, 1)

    return {
        "status_data": status_data,
        "aging_data": _build_aging_data(today),
        "avg_days_to_payment": _compute_avg_days_to_payment(),
        "collection_rate": collection_rate,
    }
