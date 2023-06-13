from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import ListView

from customer_applications.models import DocApplication


class DocApplicationListView(PermissionRequiredMixin, ListView):
    permission_required = ("customer_applications.view_docapplication",)
    model = DocApplication
    paginate_by = 15
    template_name = "customer_applications/docapplication_list.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q")
        if query and self.model is not None:
            queryset = self.model.objects.search_doc_applications(query)
        return queryset
