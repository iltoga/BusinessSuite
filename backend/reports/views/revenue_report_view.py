from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.utils import timezone
from django.views.generic import TemplateView

from invoices.models import Invoice
from payments.models import Payment
from reports.utils import format_currency, get_month_list


class RevenueReportView(LoginRequiredMixin, TemplateView):
    """Monthly and yearly revenue report with filtering."""

    template_name = "reports/revenue_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get filter parameters
        from_date_str = self.request.GET.get("from_date")
        to_date_str = self.request.GET.get("to_date")

        # Default to current year if not specified
        now = timezone.now()
        if from_date_str:
            from_date = datetime.strptime(from_date_str, "%Y-%m-%d")
        else:
            from_date = now.replace(month=1, day=1)

        if to_date_str:
            to_date = datetime.strptime(to_date_str, "%Y-%m-%d")
        else:
            to_date = now

        # Get month list
        months = get_month_list(from_date, to_date)

        # Calculate revenue data for each month
        monthly_revenue = []
        monthly_payments = []

        for month_data in months:
            month_start = month_data["date"]
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1)

            # Invoiced amount
            invoiced = Invoice.objects.filter(invoice_date__gte=month_start, invoice_date__lt=month_end).aggregate(
                total=Sum("total_amount")
            )["total"] or Decimal("0")

            # Actual payments received
            paid = Payment.objects.filter(payment_date__gte=month_start, payment_date__lt=month_end).aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0")

            monthly_revenue.append(
                {
                    "label": month_data["label"],
                    "invoiced": float(invoiced),
                    "paid": float(paid),
                }
            )

            monthly_payments.append(float(paid))

        # Calculate totals
        total_invoiced = Invoice.objects.filter(invoice_date__gte=from_date, invoice_date__lte=to_date).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0")

        total_paid = Payment.objects.filter(payment_date__gte=from_date, payment_date__lte=to_date).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0")

        total_outstanding = total_invoiced - total_paid

        # Year-over-year comparison if viewing full year
        yoy_data = None
        if (to_date - from_date).days >= 365:
            prev_year_start = from_date.replace(year=from_date.year - 1)
            prev_year_end = to_date.replace(year=to_date.year - 1)

            prev_year_revenue = Invoice.objects.filter(
                invoice_date__gte=prev_year_start, invoice_date__lte=prev_year_end
            ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0")

            if prev_year_revenue > 0:
                yoy_change = ((total_invoiced - prev_year_revenue) / prev_year_revenue) * 100
                yoy_data = {
                    "previous_year": float(prev_year_revenue),
                    "current_year": float(total_invoiced),
                    "change_percent": float(yoy_change),
                }

        context.update(
            {
                "from_date": from_date.strftime("%Y-%m-%d"),
                "to_date": to_date.strftime("%Y-%m-%d"),
                "monthly_revenue": monthly_revenue,
                "total_invoiced": total_invoiced,
                "total_invoiced_formatted": format_currency(total_invoiced),
                "total_paid": total_paid,
                "total_paid_formatted": format_currency(total_paid),
                "total_outstanding": total_outstanding,
                "total_outstanding_formatted": format_currency(total_outstanding),
                "collection_rate": (float(total_paid) / float(total_invoiced) * 100) if total_invoiced > 0 else 0,
                "yoy_data": yoy_data,
            }
        )

        return context
