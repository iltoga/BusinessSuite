from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.views import View

from customer_applications.models import DocApplication


class DocApplicationDeleteAllView(PermissionRequiredMixin, View):
    """
    Superuser-only view to delete all customer applications.
    Requires confirmation via POST request.
    """

    permission_required = ("customer_applications.delete_docapplication",)

    def dispatch(self, request, *args, **kwargs):
        # Only superusers can access this view
        if not request.user.is_superuser:
            messages.error(request, "You do not have permission to perform this action.")
            return redirect("customer-application-list")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Delete all customer applications."""
        try:
            count = DocApplication.objects.count()
            with transaction.atomic():
                DocApplication.objects.all().delete()
            messages.success(request, f"Successfully deleted {count} customer application(s).")
        except Exception as e:
            messages.error(request, f"Error deleting customer applications: {str(e)}")

        return redirect("customer-application-list")
