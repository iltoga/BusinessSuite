from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.generic import TemplateView

from customer_applications.models import DocApplication
from invoices.models.invoice import Invoice
from products.models import Product
from reports.utils import format_currency, get_month_list


class ProductRevenueAnalysisView(LoginRequiredMixin, TemplateView):
    """Product performance, revenue, and profit breakdown."""

    template_name = "reports/product_revenue_analysis.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        money_field = DecimalField(max_digits=14, decimal_places=2)
        zero_value = Value(Decimal("0.00"), output_field=money_field)

        product_unit_profit_expression = ExpressionWrapper(
            Coalesce(F("retail_price"), zero_value) - Coalesce(F("base_price"), zero_value),
            output_field=money_field,
        )

        # Get all products with revenue stats and realized profit baseline.
        products = (
            Product.objects.annotate(
                application_count=Count("doc_applications", distinct=True),
                invoiced_application_count=Count("doc_applications__invoice_applications", distinct=True),
                total_revenue=Coalesce(Sum("doc_applications__invoice_applications__amount"), zero_value),
                unit_profit=product_unit_profit_expression,
            )
            .order_by("-total_revenue", "name")
            .all()
        )

        product_data = []
        for product in products:
            invoiced_count = product.invoiced_application_count or 0
            total_revenue = product.total_revenue or Decimal("0.00")
            unit_profit = product.unit_profit or Decimal("0.00")
            total_profit = unit_profit * Decimal(invoiced_count)
            avg_price = total_revenue / invoiced_count if invoiced_count > 0 else Decimal("0.00")
            profit_margin_percent = (unit_profit / product.retail_price * Decimal("100")) if product.retail_price else Decimal(
                "0.00"
            )

            product_data.append(
                {
                    "product": product,
                    "code": product.code,
                    "name": product.name,
                    "type": product.get_product_type_display(),
                    "product_type": product.product_type,
                    "application_count": product.application_count,
                    "invoiced_application_count": invoiced_count,
                    "total_revenue": total_revenue,
                    "total_revenue_formatted": format_currency(total_revenue),
                    "avg_price": avg_price,
                    "avg_price_formatted": format_currency(avg_price),
                    "base_price": product.base_price,
                    "base_price_formatted": (
                        format_currency(product.base_price) if product.base_price is not None else "N/A"
                    ),
                    "retail_price": product.retail_price,
                    "retail_price_formatted": (
                        format_currency(product.retail_price) if product.retail_price is not None else "N/A"
                    ),
                    "unit_profit": unit_profit,
                    "unit_profit_formatted": format_currency(unit_profit),
                    "total_profit": total_profit,
                    "total_profit_formatted": format_currency(total_profit),
                    "profit_margin_percent": round(float(profit_margin_percent), 2),
                }
            )

        # Product type comparison
        type_data = []
        for type_code, type_label in Product.PRODUCT_TYPE_CHOICES:
            rows = [row for row in product_data if row["product_type"] == type_code]
            count = len(rows)
            revenue = sum((row["total_revenue"] for row in rows), Decimal("0.00"))
            total_profit = sum((row["total_profit"] for row in rows), Decimal("0.00"))
            margin = (total_profit / revenue * Decimal("100")) if revenue else Decimal("0.00")

            type_data.append(
                {
                    "type": type_label,
                    "count": count,
                    "revenue": float(revenue),
                    "revenue_formatted": format_currency(revenue),
                    "total_profit": float(total_profit),
                    "total_profit_formatted": format_currency(total_profit),
                    "profit_margin_percent": round(float(margin), 2),
                }
            )

        # Monthly trend for top 5 products (last 6 months)
        now = timezone.now()
        start_date = now.replace(day=1)
        months = get_month_list(
            start_date.replace(
                month=start_date.month - 5 if start_date.month > 5 else start_date.month + 7,
                year=start_date.year if start_date.month > 5 else start_date.year - 1,
            ),
            now,
        )

        top_products = products.filter(total_revenue__gt=0)[:5]
        monthly_trends = []
        monthly_profit_trends = []

        monthly_profit_expression = ExpressionWrapper(
            Coalesce(F("product__retail_price"), zero_value) - Coalesce(F("product__base_price"), zero_value),
            output_field=money_field,
        )

        for month_data in months:
            month_start = month_data["date"]
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1)

            trends = {"label": month_data["label"]}
            for product in top_products:
                revenue = (
                    DocApplication.objects.filter(product=product, doc_date__gte=month_start, doc_date__lt=month_end)
                    .aggregate(total=Coalesce(Sum("invoice_applications__amount"), zero_value))
                    .get("total")
                    or Decimal("0.00")
                )
                trends[product.code] = float(revenue)
            monthly_trends.append(trends)

            month_profit = (
                DocApplication.objects.filter(doc_date__gte=month_start, doc_date__lt=month_end)
                .aggregate(total=Coalesce(Sum(monthly_profit_expression), zero_value))
                .get("total")
                or Decimal("0.00")
            )
            monthly_profit_trends.append(
                {
                    "label": month_data["label"],
                    "total_profit": month_profit,
                    "total_profit_formatted": format_currency(month_profit),
                }
            )

        invoice_profit_expression = ExpressionWrapper(
            Coalesce(F("invoice_applications__customer_application__product__retail_price"), zero_value)
            - Coalesce(F("invoice_applications__customer_application__product__base_price"), zero_value),
            output_field=money_field,
        )

        invoice_profit_data = []
        invoice_rows = (
            Invoice.objects.select_related("customer")
            .annotate(
                application_count=Count("invoice_applications", distinct=True),
                total_profit=Coalesce(Sum(invoice_profit_expression), zero_value),
            )
            .order_by("-invoice_date", "-invoice_no")[:20]
        )
        for invoice in invoice_rows:
            total_profit = invoice.total_profit or Decimal("0.00")
            total_amount = invoice.total_amount or Decimal("0.00")
            margin = (total_profit / total_amount * Decimal("100")) if total_amount else Decimal("0.00")
            invoice_profit_data.append(
                {
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.invoice_no_display,
                    "invoice_date": invoice.invoice_date,
                    "customer_name": invoice.customer.full_name_with_company if invoice.customer else "",
                    "total_amount": total_amount,
                    "total_amount_formatted": format_currency(total_amount),
                    "application_count": invoice.application_count,
                    "profit": total_profit,
                    "profit_formatted": format_currency(total_profit),
                    "profit_margin_percent": round(float(margin), 2),
                }
            )

        total_products = len(product_data)
        total_revenue = sum((row["total_revenue"] for row in product_data), Decimal("0.00"))
        total_profit = sum((row["total_profit"] for row in product_data), Decimal("0.00"))
        total_applications = sum((row["application_count"] for row in product_data), 0)
        overall_margin_percent = (total_profit / total_revenue * Decimal("100")) if total_revenue else Decimal("0.00")

        context.update(
            {
                "product_data": product_data,
                "type_data": type_data,
                "monthly_trends": monthly_trends,
                "monthly_profit_trends": monthly_profit_trends,
                "invoice_profit_data": invoice_profit_data,
                "top_products": [p.code for p in top_products],
                "total_products": total_products,
                "total_revenue": total_revenue,
                "total_revenue_formatted": format_currency(total_revenue),
                "total_profit": total_profit,
                "total_profit_formatted": format_currency(total_profit),
                "overall_profit_margin_percent": round(float(overall_margin_percent), 2),
                "total_applications": total_applications,
            }
        )

        return context
