from django.shortcuts import redirect
from django.urls import reverse_lazy

from core.components.unicorn_search_list_view import UnicornSearchListView
from customers.models import Customer


class CustomerListView(UnicornSearchListView):
    model = Customer
    model_search_method = "search_customers"
    hide_disabled = True

    def handle_hide_disabled(self):
        # Trigger a new search when hide_disabled value changes
        self.search()

    def apply_filters(self, queryset):
        # Call parent class method first
        queryset = super().apply_filters(queryset)
        # Apply filters based on component's state
        queryset = self.apply_status_filters(queryset)
        return queryset

    def apply_status_filters(self, queryset):
        """Exclude records based on their status."""
        if self.hide_disabled:
            queryset = queryset.exclude(active=False)
        return queryset

    def toggle_active_status(self, pk):
        customer = Customer.objects.get(pk=pk)
        customer.active = not customer.active
        customer.save()
        return redirect(reverse_lazy("customer-list"))
