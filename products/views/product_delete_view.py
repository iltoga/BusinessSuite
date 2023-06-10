from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import DeleteView
from products.models import Product

class ProductDeleteView(PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    permission_required = ('products.delete_product',)
    model = Product
    template_name = "products/product_confirm_delete.html"
    success_url = reverse_lazy('product-list')
    success_message = "Product deleted successfully!"
