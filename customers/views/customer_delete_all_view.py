from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.views import View

from customers.models import Customer


class CustomerDeleteAllView(PermissionRequiredMixin, View):
    """
    Superuser-only view to delete all customers.
    Requires confirmation via POST request.
    """

    permission_required = ("customers.delete_customer",)

    def dispatch(self, request, *args, **kwargs):
        # Only superusers can access this view
        if not request.user.is_superuser:
            messages.error(request, "You do not have permission to perform this action.")
            return redirect("customer-list")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Delete all customers."""
        try:
            count = Customer.objects.count()
            with transaction.atomic():
                Customer.objects.all().delete()
            messages.success(request, f"Successfully deleted {count} customer(s).")
        except Exception as e:
            messages.error(request, f"Error deleting customers: {str(e)}")

        return redirect("customer-list")
