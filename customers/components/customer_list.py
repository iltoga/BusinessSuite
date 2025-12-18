from datetime import timedelta

from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone

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

    def load_items(self):
        # Use parent method to populate list_items with PKs
        super().load_items()

    def get_items(self):
        """Return actual Customer instances with passport expiration flags."""
        customers = super().get_items()
        # Add a flag to each customer indicating if passport expiration is within next 6 months
        now = timezone.now().date()
        threshold = now + timedelta(days=183)  # approx 6 months
        for cust in customers:
            cust.passport_expiring_soon = False
            cust.passport_expired = False
            if hasattr(cust, "passport_expiration_date") and cust.passport_expiration_date:
                try:
                    exp_date = cust.passport_expiration_date
                    if exp_date < now:
                        cust.passport_expired = True
                    elif exp_date <= threshold:
                        cust.passport_expiring_soon = True
                except Exception:
                    cust.passport_expiring_soon = False
                    cust.passport_expired = False
        return customers
