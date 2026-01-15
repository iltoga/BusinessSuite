from django.views.generic import DetailView

from customers.models import Customer


class CustomerDetailView(DetailView):
    model = Customer
    template_name = "customers/customer_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["uninvoiced_applications"] = (
            self.object.doc_applications.filter(invoice_applications__isnull=True)
            .select_related("product")
            .prefetch_related("invoice_applications__invoice")
            .distinct()
        )
        return context
