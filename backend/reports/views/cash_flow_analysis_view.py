from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.utils import timezone
from django.views.generic import TemplateView

from payments.models import Payment
from reports.utils import format_currency, get_month_list


class CashFlowAnalysisView(LoginRequiredMixin, TemplateView):
    """Payment tracking by type and date."""

    template_name = "reports/cash_flow_analysis.html"

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

        # Payment by type
        payment_type_data = []
        for type_code, type_label in Payment.PAYMENT_TYPES:
            payments = Payment.objects.filter(
                payment_date__gte=from_date, payment_date__lte=to_date, payment_type=type_code
            )
            count = payments.count()
            total = payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")

            payment_type_data.append(
                {"type": type_label, "count": count, "total": float(total), "total_formatted": format_currency(total)}
            )

        # Monthly cash flow
        months = get_month_list(from_date, to_date)
        monthly_cashflow = []

        for month_data in months:
            month_start = month_data["date"]
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1)

            payments = Payment.objects.filter(payment_date__gte=month_start, payment_date__lt=month_end)

            total = payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
            count = payments.count()

            monthly_cashflow.append(
                {
                    "label": month_data["label"],
                    "total": float(total),
                    "count": count,
                }
            )

        # Running balance (cumulative)
        running_balance = []
        cumulative = 0
        for data in monthly_cashflow:
            cumulative += data["total"]
            running_balance.append({"label": data["label"], "balance": cumulative})

        # Daily cash flow for last 30 days
        thirty_days_ago = now - timedelta(days=30)
        daily_payments = (
            Payment.objects.filter(payment_date__gte=thirty_days_ago)
            .values("payment_date")
            .annotate(total=Sum("amount"))
            .order_by("payment_date")
        )

        daily_cashflow = []
        for payment in daily_payments:
            daily_cashflow.append(
                {"date": payment["payment_date"].strftime("%Y-%m-%d"), "total": float(payment["total"])}
            )

        # Summary statistics
        total_cashflow = sum(m["total"] for m in monthly_cashflow)
        avg_monthly_cashflow = total_cashflow / len(monthly_cashflow) if monthly_cashflow else 0
        total_transactions = sum(m["count"] for m in monthly_cashflow)

        context.update(
            {
                "from_date": from_date.strftime("%Y-%m-%d"),
                "to_date": to_date.strftime("%Y-%m-%d"),
                "payment_type_data": payment_type_data,
                "monthly_cashflow": monthly_cashflow,
                "running_balance": running_balance,
                "daily_cashflow": daily_cashflow,
                "total_cashflow": total_cashflow,
                "total_cashflow_formatted": format_currency(total_cashflow),
                "avg_monthly_cashflow": avg_monthly_cashflow,
                "avg_monthly_cashflow_formatted": format_currency(avg_monthly_cashflow),
                "total_transactions": total_transactions,
            }
        )

        return context
