from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import DeleteView

from customers.models import Customer


class CustomerDeleteView(PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    permission_required = ("customers.delete_customer",)
    model = Customer
    template_name = "customers/customer_confirm_delete.html"
    success_url = reverse_lazy("customer-list")
    success_message = "Customer deleted successfully!"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.get_object()
        # Block deletion if customer has related invoices
        if obj.invoices.exists():
            messages.error(self.request, "Cannot delete this customer: related invoices exist.")
            context["deletion_blocked"] = True
        # Show warning before deletion if customer has related applications
        elif obj.doc_applications.exists():
            messages.warning(
                self.request, "Warning: this customer has related applications. They will be deleted as well."
            )
        return context

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.invoices.exists():
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
