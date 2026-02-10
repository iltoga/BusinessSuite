from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.utils import timezone
from django.views.generic import TemplateView

from customer_applications.models import DocApplication
from products.models import Product
from reports.utils import get_month_list


class ProductDemandForecastView(LoginRequiredMixin, TemplateView):
    """Seasonal trends and demand predictions."""

    template_name = "reports/product_demand_forecast.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        now = timezone.now()

        # Get historical data for last 12 months
        start_date = now.replace(day=1) - timedelta(days=365)
        months = get_month_list(start_date, now)

        # Get top 5 products by application count
        top_products = Product.objects.annotate(app_count=Count("doc_applications")).order_by("-app_count")[:5]

        # Monthly demand for each product
        product_demand = {}
        for product in top_products:
            monthly_data = []

            for month_data in months:
                month_start = month_data["date"]
                if month_start.month == 12:
                    month_end = month_start.replace(year=month_start.year + 1, month=1)
                else:
                    month_end = month_start.replace(month=month_start.month + 1)

                count = DocApplication.objects.filter(
                    product=product, doc_date__gte=month_start, doc_date__lt=month_end
                ).count()

                monthly_data.append({"label": month_data["label"], "count": count})

            product_demand[product.code] = {"name": product.name, "data": monthly_data}

        # Calculate growth rates (month-over-month)
        growth_rates = {}
        for product_code, demand_data in product_demand.items():
            data = demand_data["data"]
            if len(data) >= 2:
                last_month = data[-1]["count"]
                prev_month = data[-2]["count"]

                if prev_month > 0:
                    growth_rate = ((last_month - prev_month) / prev_month) * 100
                else:
                    growth_rate = 100.0 if last_month > 0 else 0.0

                growth_rates[product_code] = round(growth_rate, 1)
            else:
                growth_rates[product_code] = 0.0

        # Simple forecast for next 3 months (using moving average)
        forecast_data = {}
        for product_code, demand_data in product_demand.items():
            historical = [d["count"] for d in demand_data["data"]]

            # Use last 3 months as moving average
            if len(historical) >= 3:
                avg = sum(historical[-3:]) / 3
            elif len(historical) > 0:
                avg = sum(historical) / len(historical)
            else:
                avg = 0

            # Apply growth rate to forecast
            growth = growth_rates.get(product_code, 0) / 100

            forecasts = []
            current_forecast = avg
            for i in range(1, 4):
                current_forecast = current_forecast * (1 + growth)

                # Generate future month label
                future_month = now.month + i
                future_year = now.year
                while future_month > 12:
                    future_month -= 12
                    future_year += 1

                month_label = datetime(future_year, future_month, 1).strftime("%b %Y")

                forecasts.append({"label": month_label, "count": round(current_forecast)})

            forecast_data[product_code] = forecasts

        # Seasonal pattern detection (quarterly averages)
        quarterly_data = {}
        for product_code, demand_data in product_demand.items():
            quarters = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}

            for month_data in demand_data["data"]:
                month_num = datetime.strptime(month_data["label"], "%b %Y").month
                if month_num in [1, 2, 3]:
                    quarters["Q1"].append(month_data["count"])
                elif month_num in [4, 5, 6]:
                    quarters["Q2"].append(month_data["count"])
                elif month_num in [7, 8, 9]:
                    quarters["Q3"].append(month_data["count"])
                else:
                    quarters["Q4"].append(month_data["count"])

            quarterly_avg = {}
            for quarter, counts in quarters.items():
                quarterly_avg[quarter] = sum(counts) / len(counts) if counts else 0

            quarterly_data[product_code] = quarterly_avg

        # Total applications trend
        total_by_month = []
        for month_data in months:
            month_start = month_data["date"]
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1)

            count = DocApplication.objects.filter(doc_date__gte=month_start, doc_date__lt=month_end).count()

            total_by_month.append({"label": month_data["label"], "count": count})

        context.update(
            {
                "top_products": [p.code for p in top_products],
                "product_demand": product_demand,
                "growth_rates": growth_rates,
                "forecast_data": forecast_data,
                "quarterly_data": quarterly_data,
                "total_by_month": total_by_month,
            }
        )

        return context
