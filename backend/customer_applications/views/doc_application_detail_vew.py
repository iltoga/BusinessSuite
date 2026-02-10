from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import DetailView

from customer_applications.models import DocApplication


class DocApplicationDetailView(PermissionRequiredMixin, DetailView):
    permission_required = ("customer_applications.view_docapplication",)
    model = DocApplication
    template_name = "customer_applications/docapplication_detail.html"
    field_permissions = {
        "created_by": ["customer_applications.can_audit"],
        "created_at": ["customer_applications.can_audit"],
        "updated_at": ["customer_applications.can_audit"],
    }
