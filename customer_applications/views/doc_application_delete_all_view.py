from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.views import View

from customer_applications.models import DocApplication


class DocApplicationDeleteAllView(PermissionRequiredMixin, View):
    """
    Superuser-only view to delete selected customer applications based on search query.
    If no query is provided, deletes all customer applications.
    Requires confirmation via POST request.
    """

    permission_required = ("customer_applications.delete_docapplication",)

    def dispatch(self, request, *args, **kwargs):
        # Only superusers can access this view
        if not request.user.is_superuser:
            messages.error(request, "You do not have permission to perform this action.")
            return redirect("customer-application-list")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self, query=None, hide_finished=True, hide_not_started=False):
        """
        Get the queryset of customer applications to delete based on search query.
        Applies the same filters as the DocapplicationListView component.
        """
        if query:
            queryset = DocApplication.objects.search_doc_applications(query)
        else:
            queryset = DocApplication.objects.all()

        # Apply status filters
        if hide_finished:
            queryset = queryset.exclude(status="completed")
        if hide_not_started:
            from django.db.models import Exists, OuterRef

            from customer_applications.models.doc_workflow import DocWorkflow

            has_workflow = Exists(DocWorkflow.objects.filter(doc_application=OuterRef("pk")))
            queryset = queryset.filter(has_workflow)

        return queryset

    def post(self, request, *args, **kwargs):
        """Delete selected customer applications based on search query."""
        query = request.POST.get("search_query", "").strip()
        hide_finished = request.POST.get("hide_finished", "true") == "true"
        hide_not_started = request.POST.get("hide_not_started", "false") == "true"

        try:
            queryset = self.get_queryset(query=query, hide_finished=hide_finished, hide_not_started=hide_not_started)
            count = queryset.count()

            if count == 0:
                messages.warning(request, "No customer applications found matching the criteria.")
                return redirect("customer-application-list")

            with transaction.atomic():
                # Delete one by one to trigger signals and cleanup
                for doc_app in queryset.iterator():
                    doc_app.delete()

            if query:
                messages.success(request, f"Successfully deleted {count} customer application(s) matching '{query}'.")
            else:
                messages.success(request, f"Successfully deleted {count} customer application(s).")
        except Exception as e:
            messages.error(request, f"Error deleting customer applications: {str(e)}")

        return redirect("customer-application-list")
