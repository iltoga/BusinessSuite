from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.views import View

from products.models import Product


class ProductDeleteAllView(PermissionRequiredMixin, View):
    """
    Superuser-only view to delete all products.
    Requires confirmation via POST request.
    """

    permission_required = ("products.delete_product",)

    def dispatch(self, request, *args, **kwargs):
        # Only superusers can access this view
        if not request.user.is_superuser:
            messages.error(request, "You do not have permission to perform this action.")
            return redirect("product-list")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Delete all products."""
        try:
            count = Product.objects.count()
            with transaction.atomic():
                Product.objects.all().delete()
            messages.success(request, f"Successfully deleted {count} product(s).")
        except Exception as e:
            messages.error(request, f"Error deleting products: {str(e)}")

        return redirect("product-list")
