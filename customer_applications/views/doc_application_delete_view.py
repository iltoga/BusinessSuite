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
        # If application has related invoices, show warning and checkbox to allow superuser cascade delete
        if obj.invoice_applications.exists():
            messages.warning(
                self.request,
                "This application has linked invoices. Check the box below to also delete the linked invoice(s) (superusers only).",
            )
            context["has_linked_invoices"] = True
        return context

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        delete_invoices = request.POST.get("delete_invoices") == "yes"

        can_delete, msg = obj.can_be_deleted(user=request.user, delete_invoices=delete_invoices)
        if not can_delete:
            messages.error(request, msg)
            self.object = obj  # Fix: set self.object for get_context_data
            return self.render_to_response(self.get_context_data())

        # Proceed with deletion; if delete_invoices requested and user is superuser, cleanup invoices
        if delete_invoices and request.user.is_superuser:
            # collect related invoices prior to deletion
            invoice_ids = list(obj.invoice_applications.values_list("invoice_id", flat=True).distinct())
            try:
                from django.db import transaction

                from invoices.models.invoice import Invoice

                with transaction.atomic():
                    # delete the application (cascade will delete InvoiceApplication rows)
                    obj.delete(force_delete_invoices=True, user=request.user)

                    # cleanup invoices: delete invoices that no longer have any InvoiceApplication or recalc others
                    for inv_id in invoice_ids:
                        invoice = Invoice.objects.filter(pk=inv_id).first()
                        if not invoice:
                            continue
                        if invoice.invoice_applications.count() == 0:
                            # force delete invoice (superuser confirmation already present)
                            invoice.delete(force=True)
                        else:
                            # recompute totals/status
                            invoice.save()
            except Exception as e:
                messages.error(request, f"Error deleting application and linked invoices: {e}")
                self.object = obj
                return self.render_to_response(self.get_context_data())

            messages.success(request, self.success_message)
            return self.redirect_success_url()

        # Default behaviour (no linked invoice deletion)
        if obj.invoice_applications.exists() and not delete_invoices:
            self.object = obj
            return self.render_to_response(self.get_context_data())

        # Perform the deletion normally
        return super().post(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        # This method is kept for completeness but the actual deletion handling is done in post()
        return super().delete(request, *args, **kwargs)

    def redirect_success_url(self):
        from django.http import HttpResponseRedirect

        return HttpResponseRedirect(self.get_success_url())
