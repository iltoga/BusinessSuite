from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import ListView

from customers.models import Customer


class CustomerListView(PermissionRequiredMixin, ListView):
    permission_required = ("customers.view_customer",)
    model = Customer
    template_name = "customers/customer_list.html"  # Assuming your template is in this location

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q")
        if query and self.model is not None:
            queryset = self.model.objects.search_customers(query)
        return queryset
