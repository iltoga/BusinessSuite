from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import DetailView

from customer_applications.models import DocWorkflow


class DocWorkflowDetailView(PermissionRequiredMixin, DetailView):
    permission_required = ("customer_applications.view_docworkflow",)
    model = DocWorkflow
    template_name = "customer_applications/docworkflow_detail.html"
