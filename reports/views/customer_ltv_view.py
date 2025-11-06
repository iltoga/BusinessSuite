from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.views.generic import TemplateView

from customers.models import Customer
from reports.utils import format_currency


class CustomerLifetimeValueView(LoginRequiredMixin, TemplateView):
    """Customer ranking by revenue and statistics."""

    template_name = "reports/customer_ltv.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all customers with their revenue stats
        # Use distinct=True to avoid duplication when customer has multiple related records
        customers = Customer.objects.annotate(
            total_revenue=Sum("invoices__total_amount", distinct=True),
            invoice_count=Count("invoices", distinct=True),
            application_count=Count("doc_applications", distinct=True),
        ).order_by("-total_revenue")

        # Filter out customers with no revenue
        customers_with_revenue = customers.filter(total_revenue__isnull=False, total_revenue__gt=0)

        # Calculate average invoice value
        customer_data = []
        for customer in customers_with_revenue:
            avg_invoice = (
                customer.total_revenue / customer.invoice_count if customer.invoice_count > 0 else Decimal("0")
            )

            # Calculate customer tenure (days since first invoice)
            first_invoice = customer.invoices.order_by("invoice_date").first()
            from django.utils import timezone

            if first_invoice:
                tenure_days = (timezone.now().date() - first_invoice.invoice_date).days
            else:
                tenure_days = 0

            customer_data.append(
                {
                    "customer": customer,
                    "customer_name": customer.full_name,
                    "customer_id": customer.id,
                    "total_revenue": float(customer.total_revenue),
                    "total_revenue_formatted": format_currency(customer.total_revenue),
                    "invoice_count": customer.invoice_count,
                    "application_count": customer.application_count,
                    "avg_invoice": float(avg_invoice),
                    "avg_invoice_formatted": format_currency(avg_invoice),
                    "tenure_days": tenure_days,
                    "first_purchase": first_invoice.invoice_date.strftime("%Y-%m-%d") if first_invoice else None,
                }
            )

        # Top 10 customers
        top_customers = customer_data[:10]

        # Create JSON-safe version for charts (without Customer model instances)
        top_customers_json = [
            {
                "customer_name": c["customer_name"],
                "customer_id": c["customer_id"],
                "total_revenue": c["total_revenue"],
                "total_revenue_formatted": c["total_revenue_formatted"],
                "invoice_count": c["invoice_count"],
                "application_count": c["application_count"],
                "avg_invoice": c["avg_invoice"],
                "avg_invoice_formatted": c["avg_invoice_formatted"],
                "tenure_days": c["tenure_days"],
                "first_purchase": c["first_purchase"],
            }
            for c in top_customers
        ]

        # Summary statistics
        total_customers = customers_with_revenue.count()
        total_revenue = sum(c["total_revenue"] for c in customer_data)
        avg_customer_value = total_revenue / total_customers if total_customers > 0 else Decimal("0")

        # Customer segmentation (by revenue)
        high_value = len([c for c in customer_data if c["total_revenue"] >= avg_customer_value * 2])
        medium_value = len(
            [c for c in customer_data if avg_customer_value <= c["total_revenue"] < avg_customer_value * 2]
        )
        low_value = len([c for c in customer_data if c["total_revenue"] < avg_customer_value])

        context.update(
            {
                "top_customers": top_customers_json,  # JSON-safe version for charts
                "all_customers": customer_data[:50],  # Keep full version for template display
                "total_customers": total_customers,
                "total_revenue": total_revenue,
                "total_revenue_formatted": format_currency(total_revenue),
                "avg_customer_value": avg_customer_value,
                "avg_customer_value_formatted": format_currency(avg_customer_value),
                "high_value_count": high_value,
                "medium_value_count": medium_value,
                "low_value_count": low_value,
            }
        )

        return context
