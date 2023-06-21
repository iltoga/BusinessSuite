from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from customer_applications.forms import DocumentUpdateForm
from customer_applications.models import Document


class DocumentUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ("customer_applications.change_document",)
    model = Document
    form_class = DocumentUpdateForm
    template_name = "customer_applications/document_update.html"
    success_message = "Required document updated successfully!"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context["form"]
        context["product_doc_type"] = form.instance.doc_type
        return context

    def get_initial(self):
        initial = super().get_initial()
        # Only set 'ocr_check' field to False when the form is initially displayed
        initial["ocr_check"] = False
        # Reset metadata so that if we don't hit ocr check button and save, the metadata will be reset to None
        initial["metadata"] = None
        # if doc_type.name is "Address" and details field is empty, take the address from the customer
        if self.object.doc_type.name == "Address" and (not self.object.details or self.object.details == ""):
            initial["details"] = self.object.doc_application.customer.address_bali

        if self.object.doc_type.name == "Passport" and not self.object.file and not self.object.file_link:
            document = (
                Document.objects.filter(
                    doc_application__customer__pk=self.object.doc_application.customer.pk,
                    doc_type__name="Passport",
                    completed=True,
                )
                .order_by("-updated_at")
                .first()
            )

            if document:
                if document.is_expiring:
                    messages.warning(
                        self.request, "We have a previous Passport, but is expiring soon. Please upload a new one."
                    )
                elif document.is_expired:
                    messages.warning(
                        self.request, "We have a previous Passport, but is already expired. Please upload a new one."
                    )
                else:
                    initial["file"] = document.file
                    initial["file_link"] = document.file_link
                    initial["doc_number"] = document.doc_number
                    initial["expiration_date"] = document.expiration_date
                    initial["ocr_check"] = document.ocr_check
                    initial["details"] = document.details
                    initial["metadata"] = document.metadata
                    messages.success(self.request, "Data imported from previous Customer's application")
        return initial

    def form_valid(self, form):
        if form.instance.pk is None:
            form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("customer-application-detail", kwargs={"pk": self.object.doc_application.id})
