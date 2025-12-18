from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import ListView

from customers.models import Customer


class CustomerListView(PermissionRequiredMixin, ListView):
    permission_required = ("customers.view_customer",)
    model = Customer
    template_name = "customers/customer_list.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q")
        if query and self.model is not None:
            # Use model's default ordering (by creation date, newest first)
            order_by = self.model._meta.ordering or []
            queryset = self.model.objects.search_customers(query).order_by(*order_by)
        # Queryset already inherits the model's Meta.ordering
        return queryset
