from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import DeleteView

from customer_applications.models import DocApplication


class DocApplicationDeleteView(PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    permission_required = ("customer_applications.delete_docapplication",)
    model = DocApplication
    template_name = "customer_applications/docapplication_delete.html"
    success_url = reverse_lazy("customer-application-list")
    success_message = "Customer application deleted successfully!"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.get_object()
        # Block deletion if application has related invoices
        if obj.invoice_applications.exists():
            messages.error(self.request, "Cannot delete this application: related invoices exist.")
            context["deletion_blocked"] = True
        return context

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.invoice_applications.exists():
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
