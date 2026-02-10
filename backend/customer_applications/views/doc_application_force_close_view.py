from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from customer_applications.models import DocApplication


class DocApplicationForceCloseView(PermissionRequiredMixin, View):
    """
    View to force close a customer application even if not all required documents
    have been uploaded or linked to it.
    """

    permission_required = ("customer_applications.change_docapplication",)

    def post(self, request, *args, **kwargs):
        doc_application_id = kwargs.get("pk")
        doc_application = get_object_or_404(DocApplication, pk=doc_application_id)

        # Force set the status to completed
        doc_application.status = DocApplication.STATUS_COMPLETED
        doc_application.save(skip_status_calculation=True)

        messages.success(
            request,
            f"Application #{doc_application.pk} for {doc_application.customer.full_name} "
            f"has been force closed successfully.",
        )

        # Redirect back to the referrer or the list view
        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
        if next_url:
            return redirect(next_url)
        return redirect("customer-application-list")
