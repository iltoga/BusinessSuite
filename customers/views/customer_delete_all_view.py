from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.views import View

from customers.models import Customer


class CustomerDeleteAllView(PermissionRequiredMixin, View):
    """
    Superuser-only view to delete selected customers based on search query.
    If no query is provided, deletes all customers.
    Requires confirmation via POST request.
    """

    permission_required = ("customers.delete_customer",)

    def dispatch(self, request, *args, **kwargs):
        # Only superusers can access this view
        if not request.user.is_superuser:
            messages.error(request, "You do not have permission to perform this action.")
            return redirect("customer-list")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self, query=None, hide_disabled=True):
        """
        Get the queryset of customers to delete based on search query.
        Applies the same filters as the CustomerListView component.
        """
        if query:
            queryset = Customer.objects.search_customers(query)
        else:
            queryset = Customer.objects.all()

        # Apply the hide_disabled filter if enabled
        if hide_disabled:
            queryset = queryset.exclude(active=False)

        return queryset

    def post(self, request, *args, **kwargs):
        """Delete selected customers based on search query."""
        query = request.POST.get("search_query", "").strip()
        hide_disabled = request.POST.get("hide_disabled", "true") == "true"

        try:
            queryset = self.get_queryset(query=query, hide_disabled=hide_disabled)
            count = queryset.count()

            if count == 0:
                messages.warning(request, "No customers found matching the criteria.")
                return redirect("customer-list")

            with transaction.atomic():
                # Use force=True to bypass the can_be_deleted check for superusers
                # Delete one by one to trigger signals and cleanup
                for customer in queryset.iterator():
                    customer.delete(force=True)

            if query:
                messages.success(request, f"Successfully deleted {count} customer(s) matching '{query}'.")
            else:
                messages.success(request, f"Successfully deleted {count} customer(s).")
        except Exception as e:
            messages.error(request, f"Error deleting customers: {str(e)}")

        return redirect("customer-list")
