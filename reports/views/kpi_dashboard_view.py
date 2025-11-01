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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

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

        # Revenue YTD (Year to Date)
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

        # Top 5 customers by revenue
        from customers.models import Customer

        top_customers = Customer.objects.annotate(total_revenue=Sum("invoices__total_amount")).order_by(
            "-total_revenue"
        )[:5]

        # Recent payments (last 7 days)
        recent_payments = Payment.objects.filter(payment_date__gte=now - timedelta(days=7)).order_by("-payment_date")[
            :5
        ]

        # Monthly revenue trend (last 6 months)
        monthly_data = []
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

            monthly_data.append({"label": month.strftime("%b %Y"), "revenue": float(revenue)})

        context.update(
            {
                "revenue_mtd": revenue_mtd,
                "revenue_mtd_formatted": format_currency(revenue_mtd),
                "revenue_trend": revenue_trend,
                "revenue_change": f"{revenue_change:.1f}",
                "revenue_ytd": revenue_ytd,
                "revenue_ytd_formatted": format_currency(revenue_ytd),
                "outstanding_amount": outstanding_net,
                "outstanding_formatted": format_currency(outstanding_net),
                "active_applications": active_applications,
                "overdue_invoices": overdue_invoices,
                "top_customers": top_customers,
                "recent_payments": recent_payments,
                "monthly_data": monthly_data,
            }
        )

        return context
