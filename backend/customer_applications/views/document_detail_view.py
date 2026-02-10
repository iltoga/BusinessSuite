from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import DetailView

from customer_applications.models import Document


class DocumentDetailView(PermissionRequiredMixin, DetailView):
    permission_required = ("customer_applications.view_document",)
    model = Document
    template_name = "customer_applications/document_detail.html"
