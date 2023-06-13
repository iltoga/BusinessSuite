from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import ListView

from products.models import Product


class ProductListView(PermissionRequiredMixin, ListView):
    permission_required = ("products.view_product",)
    model = Product
    context_object_name = "products"  # Default is object_list if not specified
    template_name = "products/product_list.html"
    paginate_by = 15

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q")
        if query and self.model is not None:
            queryset = self.model.objects.search_products(query)
        return queryset
