from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponseRedirect
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
        user = self.request.user
        can_delete, msg = obj.can_be_deleted(user=user)

        if not can_delete:
            messages.error(self.request, msg)
            context["deletion_blocked"] = True
        elif msg:
            # Show warning for cascade delete scenarios
            messages.warning(self.request, msg)
            context["has_related_data"] = True

        return context

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        can_delete, msg = obj.can_be_deleted(user=request.user)
        if not can_delete:
            self.object = obj
            return self.render_to_response(self.get_context_data())

        # Perform the deletion
        return self.delete(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """Override to use force=True for superuser cascade delete."""
        self.object = self.get_object()
        user = request.user

        # Check if we need to force delete (superuser with related invoices)
        force = user.is_superuser and self.object.invoices.exists()

        try:
            self.object.delete(force=force)
            messages.success(request, self.success_message)
        except Exception as e:
            messages.error(request, f"Error deleting customer: {str(e)}")
            return self.render_to_response(self.get_context_data())

        return HttpResponseRedirect(self.get_success_url())
