from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.views.generic import TemplateView

from customer_applications.models import DocApplication
from products.models import Product
from reports.utils import format_currency, get_month_list


class ProductRevenueAnalysisView(LoginRequiredMixin, TemplateView):
    """Product performance and revenue breakdown."""

    template_name = "reports/product_revenue_analysis.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all products with their revenue stats
        products = Product.objects.annotate(
            application_count=Count("doc_applications"),
            total_revenue=Sum("doc_applications__invoice_applications__amount"),
        ).order_by("-total_revenue")

        # Product data
        product_data = []
        for product in products:
            if product.total_revenue is None:
                product.total_revenue = Decimal("0")

            avg_price = (
                product.total_revenue / product.application_count if product.application_count > 0 else Decimal("0")
            )

            product_data.append(
                {
                    "product": product,
                    "code": product.code,
                    "name": product.name,
                    "type": product.get_product_type_display(),
                    "application_count": product.application_count,
                    "total_revenue": product.total_revenue,
                    "total_revenue_formatted": format_currency(product.total_revenue),
                    "avg_price": avg_price,
                    "avg_price_formatted": format_currency(avg_price),
                    "base_price": product.base_price,
                    "base_price_formatted": format_currency(product.base_price) if product.base_price else "N/A",
                }
            )

        # Product type comparison
        from django.db.models import Q

        type_data = []
        for type_code, type_label in Product.PRODUCT_TYPE_CHOICES:
            products_of_type = Product.objects.filter(product_type=type_code)
            count = products_of_type.count()
            revenue = products_of_type.annotate(rev=Sum("doc_applications__invoice_applications__amount")).aggregate(
                total=Sum("rev")
            )["total"] or Decimal("0")

            type_data.append(
                {
                    "type": type_label,
                    "count": count,
                    "revenue": float(revenue),
                    "revenue_formatted": format_currency(revenue),
                }
            )

        # Monthly trend for top 5 products (last 6 months)
        from django.utils import timezone

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

        for month_data in months:
            month_start = month_data["date"]
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1)

            trends = {"label": month_data["label"]}
            for product in top_products:
                revenue = DocApplication.objects.filter(
                    product=product, doc_date__gte=month_start, doc_date__lt=month_end
                ).aggregate(total=Sum("invoice_applications__amount"))["total"] or Decimal("0")

                trends[product.code] = float(revenue)

            monthly_trends.append(trends)

        # Summary statistics
        total_products = products.count()
        total_revenue = sum(p["total_revenue"] for p in product_data)
        total_applications = sum(p["application_count"] for p in product_data)

        context.update(
            {
                "product_data": product_data,
                "type_data": type_data,
                "monthly_trends": monthly_trends,
                "top_products": [p.code for p in top_products],
                "total_products": total_products,
                "total_revenue": total_revenue,
                "total_revenue_formatted": format_currency(total_revenue),
                "total_applications": total_applications,
            }
        )

        return context
