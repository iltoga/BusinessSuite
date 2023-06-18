from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import DetailView

from customer_applications.models import RequiredDocument


class RequiredDocumentDetailView(PermissionRequiredMixin, DetailView):
    permission_required = ("customer_applications.view_requireddocument",)
    model = RequiredDocument
    template_name = "customer_applications/requireddocument_detail.html"
