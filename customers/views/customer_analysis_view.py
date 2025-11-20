import base64
import io
from datetime import date

import seaborn as sns
from django.db.models import Count
from django.views.generic import TemplateView
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from customers.models import Customer


class CustomerAnalysisView(TemplateView):
    template_name = "customers/analysis.html"
    plot_types = {
        "nationality": {
            "function": "_prepare_nationality_data",
            "display_name": "Distribution of Customers by Nationality",
        },
        "age": {"function": "_prepare_age_data", "display_name": "Distribution of Customers' Ages"},
    }

    def get(self, request, *args, **kwargs):
        self.plot_type = kwargs.get("plot_type", "nationality")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        fig = Figure(figsize=(12, 6))
        ax = fig.add_subplot(111)

        # Load data from the Customer model
        customers = Customer.objects.all()

        # Prepare data and plot based on the plot_type
        if self.plot_type not in self.plot_types:
            raise ValueError(
                f"Invalid plot_type: {self.plot_type}. Expected one of: {', '.join(self.plot_types.keys())}"
            )

        plot_info = self.plot_types[self.plot_type]
        data_function = getattr(self, plot_info["function"])
        data = data_function(customers)

        # Plot data
        if self.plot_type == "nationality":
            sns.barplot(x=list(data.keys()), y=list(data.values()), ax=ax)
        elif self.plot_type == "age":
            sns.histplot(data, bins=30, color="skyblue", kde=True, ax=ax)

        ax.set_title(plot_info["display_name"])
        ax.set_xlabel(self.plot_type.capitalize())
        ax.set_ylabel("Number of Customers")

        # Save the plot to a BytesIO object
        buf = io.BytesIO()
        FigureCanvasAgg(fig).print_png(buf)

        # Embed the result in the html output
        data = base64.b64encode(buf.getbuffer()).decode("ascii")
        context["plot"] = f"data:image/png;base64,{data}"

        # List of available charts
        context["charts"] = list(self.plot_types.items())

        return context

    def _prepare_nationality_data(self, customers):
        from collections import defaultdict

        # Query to count the customers by nationality from the provided queryset
        count_data = customers.values("nationality__country").annotate(num_customers=Count("id"))

        # Create a dictionary to store the data
        data = defaultdict(int)
        for entry in count_data:
            country = entry["nationality__country"] or "Unknown"
            data[country] = entry["num_customers"]

        # Ensure we return a plain dict (sorted by count desc) for plotting consistency
        return dict(sorted(data.items(), key=lambda kv: kv[1], reverse=True))

    def _prepare_age_data(self, customers):
        # Ignore customers without a birthdate to avoid AttributeError
        customers_with_bd = customers.filter(birthdate__isnull=False)
        ages = [date.today().year - customer.birthdate.year for customer in customers_with_bd]
        return ages
