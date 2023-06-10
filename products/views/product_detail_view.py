from django.views.generic import DetailView
from django.contrib.auth.mixins import PermissionRequiredMixin
from products.models import Product, Task

class ProductDetailView(PermissionRequiredMixin, DetailView):
    permission_required = ('products.view_product',)
    model = Product
    template_name = "products/product_detail.html"
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tasks'] = Task.objects.filter(product=self.object)
        return context