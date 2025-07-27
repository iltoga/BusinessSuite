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
