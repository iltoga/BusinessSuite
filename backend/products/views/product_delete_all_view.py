from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.views import View

from products.models import Product


class ProductDeleteAllView(PermissionRequiredMixin, View):
    """
    Superuser-only view to delete selected products based on search query.
    If no query is provided, deletes all products.
    Requires confirmation via POST request.
    """

    permission_required = ("products.delete_product",)

    def dispatch(self, request, *args, **kwargs):
        # Only superusers can access this view
        if not request.user.is_superuser:
            messages.error(request, "You do not have permission to perform this action.")
            return redirect("product-list")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self, query=None):
        """
        Get the queryset of products to delete based on search query.
        Applies the same filters as the ProductListView component.
        """
        if query:
            queryset = Product.objects.search_products(query)
        else:
            queryset = Product.objects.all()

        return queryset

    def post(self, request, *args, **kwargs):
        """Delete selected products based on search query."""
        query = request.POST.get("search_query", "").strip()

        try:
            queryset = self.get_queryset(query=query)
            count = queryset.count()

            if count == 0:
                messages.warning(request, "No products found matching the criteria.")
                return redirect("product-list")

            with transaction.atomic():
                # Delete one by one to trigger signals
                for product in queryset.iterator():
                    product.delete()

            if query:
                messages.success(request, f"Successfully deleted {count} product(s) matching '{query}'.")
            else:
                messages.success(request, f"Successfully deleted {count} product(s).")
        except Exception as e:
            messages.error(request, f"Error deleting products: {str(e)}")

        return redirect("product-list")
