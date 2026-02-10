from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.views.generic import TemplateView

from customer_applications.models import DocApplication
from invoices.models import Invoice, InvoiceApplication
from payments.models import Payment
from reports.utils import format_currency, get_trend_indicator


class KPIDashboardView(LoginRequiredMixin, TemplateView):
    """Executive KPI Dashboard with key metrics."""

    template_name = "reports/kpi_dashboard.html"

    def get_timeframe_dates(self, timeframe, now):
        """Calculate start and end dates based on timeframe selection."""
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

        if timeframe == "6months":
            # Last 6 months
            if start_of_month.month > 6:
                period_start = start_of_month.replace(month=start_of_month.month - 6)
            else:
                period_start = start_of_month.replace(year=start_of_month.year - 1, month=12 + start_of_month.month - 6)
            period_label = "Last 6 Months"
        elif timeframe == "year":
            # Current year
            period_start = start_of_year
            period_label = "Current Year"
        else:  # all_time
            # All time - use earliest invoice date or a sensible default
            earliest_invoice = Invoice.objects.order_by("invoice_date").first()
            if earliest_invoice:
                # Convert date to datetime and set to start of month
                period_start = timezone.datetime(
                    earliest_invoice.invoice_date.year,
                    earliest_invoice.invoice_date.month,
                    1,
                    tzinfo=timezone.get_current_timezone(),
                )
            else:
                period_start = start_of_year
            period_label = "All Time"

        return period_start, now, period_label

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get timeframe from query parameter, default to "6months"
        timeframe = self.request.GET.get("timeframe", "6months")
        period_start, period_end, period_label = self.get_timeframe_dates(timeframe, now)

        # Previous month for comparison
        if start_of_month.month == 1:
            prev_month_start = start_of_month.replace(year=start_of_month.year - 1, month=12)
        else:
            prev_month_start = start_of_month.replace(month=start_of_month.month - 1)

        # Revenue MTD (Month to Date)
        revenue_mtd = Invoice.objects.filter(invoice_date__gte=start_of_month, invoice_date__lte=now).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0")

        # Revenue previous month
        revenue_prev_month = Invoice.objects.filter(
            invoice_date__gte=prev_month_start, invoice_date__lt=start_of_month
        ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0")

        revenue_trend, revenue_change = get_trend_indicator(float(revenue_mtd), float(revenue_prev_month))

        # Revenue for selected period
        revenue_period = Invoice.objects.filter(invoice_date__gte=period_start, invoice_date__lte=period_end).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0")

        # Revenue YTD (Year to Date) - always current year
        revenue_ytd = Invoice.objects.filter(invoice_date__gte=start_of_year, invoice_date__lte=now).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0")

        # Outstanding invoices
        outstanding_amount = Invoice.objects.filter(
            status__in=[Invoice.PENDING_PAYMENT, Invoice.PARTIAL_PAYMENT, Invoice.OVERDUE]
        ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0")

        outstanding_paid = Payment.objects.filter(
            invoice_application__invoice__status__in=[Invoice.PENDING_PAYMENT, Invoice.PARTIAL_PAYMENT, Invoice.OVERDUE]
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        outstanding_net = outstanding_amount - outstanding_paid

        # Active applications count
        active_applications = DocApplication.objects.filter(
            status__in=[DocApplication.STATUS_PENDING, DocApplication.STATUS_PROCESSING]
        ).count()

        # Overdue invoices
        overdue_invoices = Invoice.objects.filter(status=Invoice.OVERDUE).count()

        # Top 5 customers by revenue (for selected period)
        from customers.models import Customer

        top_customers = (
            Customer.objects.filter(invoices__invoice_date__gte=period_start, invoices__invoice_date__lte=period_end)
            .annotate(total_revenue=Sum("invoices__total_amount"))
            .order_by("-total_revenue")[:5]
        )

        # Recent payments (last 7 days)
        recent_payments = Payment.objects.filter(payment_date__gte=now - timedelta(days=7)).order_by("-payment_date")[
            :5
        ]

        # Calculate chart data based on timeframe
        chart_data = self.get_chart_data(period_start, period_end, timeframe, start_of_month)

        context.update(
            {
                "timeframe": timeframe,
                "period_label": period_label,
                "revenue_mtd": revenue_mtd,
                "revenue_mtd_formatted": format_currency(revenue_mtd),
                "revenue_trend": revenue_trend,
                "revenue_change": f"{revenue_change:.1f}",
                "revenue_period": revenue_period,
                "revenue_period_formatted": format_currency(revenue_period),
                "revenue_ytd": revenue_ytd,
                "revenue_ytd_formatted": format_currency(revenue_ytd),
                "outstanding_amount": outstanding_net,
                "outstanding_formatted": format_currency(outstanding_net),
                "active_applications": active_applications,
                "overdue_invoices": overdue_invoices,
                "top_customers": top_customers,
                "recent_payments": recent_payments,
                "chart_data": chart_data,
                "chart_label": self.get_chart_label(timeframe),
            }
        )

        return context

    def get_chart_data(self, period_start, period_end, timeframe, start_of_month):
        """Generate chart data based on timeframe."""
        chart_data = []

        if timeframe == "6months":
            # Monthly data for last 6 months
            for i in range(5, -1, -1):
                if start_of_month.month - i <= 0:
                    month = start_of_month.replace(year=start_of_month.year - 1, month=12 + (start_of_month.month - i))
                else:
                    month = start_of_month.replace(month=start_of_month.month - i)

                next_month = (
                    month.replace(month=month.month + 1)
                    if month.month < 12
                    else month.replace(year=month.year + 1, month=1)
                )

                revenue = Invoice.objects.filter(invoice_date__gte=month, invoice_date__lt=next_month).aggregate(
                    total=Sum("total_amount")
                )["total"] or Decimal("0")

                chart_data.append({"label": month.strftime("%b %Y"), "revenue": float(revenue)})

        elif timeframe == "year":
            # Monthly data for current year
            now = timezone.now()
            start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

            for month_num in range(1, 13):
                month = start_of_year.replace(month=month_num)
                next_month = (
                    month.replace(month=month.month + 1)
                    if month.month < 12
                    else month.replace(year=month.year + 1, month=1)
                )

                # Only include months up to current month
                if month > now:
                    break

                revenue = Invoice.objects.filter(invoice_date__gte=month, invoice_date__lt=next_month).aggregate(
                    total=Sum("total_amount")
                )["total"] or Decimal("0")

                chart_data.append({"label": month.strftime("%b %Y"), "revenue": float(revenue)})

        else:  # all_time
            # Yearly data for all time
            earliest_invoice = Invoice.objects.order_by("invoice_date").first()
            if earliest_invoice:
                start_year = earliest_invoice.invoice_date.year
            else:
                start_year = timezone.now().year

            current_year = timezone.now().year

            for year in range(start_year, current_year + 1):
                year_start = timezone.datetime(year, 1, 1, tzinfo=timezone.get_current_timezone())
                year_end = timezone.datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.get_current_timezone())

                revenue = Invoice.objects.filter(invoice_date__gte=year_start, invoice_date__lte=year_end).aggregate(
                    total=Sum("total_amount")
                )["total"] or Decimal("0")

                chart_data.append({"label": str(year), "revenue": float(revenue)})

        return chart_data

    def get_chart_label(self, timeframe):
        """Get appropriate chart label based on timeframe."""
        labels = {
            "6months": "Revenue Trend (Last 6 Months)",
            "year": "Revenue Trend (Current Year)",
            "all_time": "Revenue Trend (All Time)",
        }
        return labels.get(timeframe, "Revenue Trend")
