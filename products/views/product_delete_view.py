from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import DeleteView

from products.models import Product


class ProductDeleteView(PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    permission_required = ("products.delete_product",)
    model = Product
    template_name = "products/product_confirm_delete.html"
    success_url = reverse_lazy("product-list")
    success_message = "Product deleted successfully!"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.get_object()
        # Block deletion if any related customer applications have related invoices
        if (
            hasattr(obj, "doc_applications")
            and obj.doc_applications.filter(invoice_applications__isnull=False).exists()
        ):
            messages.error(self.request, "Cannot delete this product: related invoices exist.")
            context["deletion_blocked"] = True
        # Show warning before deletion if product has related applications
        elif hasattr(obj, "doc_applications") and obj.doc_applications.exists():
            messages.warning(
                self.request, "Warning: this product has related applications. They will be deleted as well."
            )
        return context

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if (
            hasattr(obj, "doc_applications")
            and obj.doc_applications.filter(invoice_applications__isnull=False).exists()
        ):
            self.object = obj  # Fix: set self.object for get_context_data
            return self.render_to_response(self.get_context_data())
        return super().post(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        can_delete, msg = obj.can_be_deleted()
        if not can_delete:
            messages.error(request, msg)
            self.object = obj  # Fix: set self.object for get_context_data
            return self.render_to_response(self.get_context_data())
        return super().delete(request, *args, **kwargs)
