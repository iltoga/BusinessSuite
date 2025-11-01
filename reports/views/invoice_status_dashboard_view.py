from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.utils import timezone
from django.views.generic import TemplateView

from invoices.models import Invoice
from reports.utils import format_currency


class InvoiceStatusDashboardView(LoginRequiredMixin, TemplateView):
    """Invoice status tracking and aging analysis."""

    template_name = "reports/invoice_status_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        now = timezone.now().date()

        # Group by status
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

        # Aging analysis (for unpaid invoices)
        # Buckets represent days overdue (past due date)
        aging_buckets = [
            {"label": "0-30 days", "min": 0, "max": 30},
            {"label": "31-60 days", "min": 31, "max": 60},
            {"label": "61-90 days", "min": 61, "max": 90},
            {"label": "90+ days", "min": 91, "max": None},  # No upper limit for 90+
        ]

        aging_data = []
        for bucket in aging_buckets:
            # Calculate date range (how many days ago was the due date)
            end_date = now - timedelta(days=bucket["min"])  # Most recent due date in range

            if bucket["max"] is not None:
                start_date = now - timedelta(days=bucket["max"])  # Oldest due date in range
                invoices = Invoice.objects.filter(
                    due_date__gte=start_date,
                    due_date__lte=end_date,
                    status__in=[Invoice.PENDING_PAYMENT, Invoice.PARTIAL_PAYMENT, Invoice.OVERDUE],
                )
            else:
                # For 90+ days, no lower bound
                invoices = Invoice.objects.filter(
                    due_date__lte=end_date,
                    status__in=[Invoice.PENDING_PAYMENT, Invoice.PARTIAL_PAYMENT, Invoice.OVERDUE],
                )

            count = invoices.count()
            total = invoices.aggregate(total=Sum("total_amount"))["total"] or Decimal("0")

            # Calculate actual outstanding (invoice amount - payments)
            outstanding = Decimal("0")
            for invoice in invoices:
                outstanding += invoice.total_due_amount

            aging_data.append(
                {
                    "label": bucket["label"],
                    "count": count,
                    "total": float(outstanding),
                    "total_formatted": format_currency(outstanding),
                }
            )

        # Average days to payment (for paid invoices only)
        from django.db.models import DurationField, ExpressionWrapper, F
        from django.db.models.functions import Coalesce

        paid_invoices = Invoice.objects.filter(status=Invoice.PAID)

        # Calculate average days manually
        total_days = 0
        count_with_payment = 0

        for invoice in paid_invoices:
            # Get first payment date
            first_payment = invoice.invoice_applications.first()
            if first_payment and first_payment.payments.exists():
                first_payment_date = first_payment.payments.order_by("payment_date").first().payment_date
                days_to_payment = (first_payment_date - invoice.invoice_date).days
                total_days += days_to_payment
                count_with_payment += 1

        avg_days_to_payment = total_days / count_with_payment if count_with_payment > 0 else 0

        # Collection rate
        all_invoices = Invoice.objects.all()
        paid_count = all_invoices.filter(status=Invoice.PAID).count()
        total_count = all_invoices.count()
        collection_rate = (paid_count / total_count * 100) if total_count > 0 else 0

        context.update(
            {
                "status_data": status_data,
                "aging_data": aging_data,
                "avg_days_to_payment": round(avg_days_to_payment, 1),
                "collection_rate": round(collection_rate, 1),
            }
        )

        return context
