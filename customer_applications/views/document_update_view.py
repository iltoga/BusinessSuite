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

    def get_success_url(self):
        return reverse_lazy("customer-application-detail", kwargs={"pk": self.object.doc_application.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product_doc_type"] = context["form"].instance.doc_type
        context["extra_actions"] = context["form"].get_extra_actions()
        return context

    def get_initial(self):
        initial = super().get_initial()
        initial = self.populate_initial_with_address(initial)
        initial = self.populate_initial_with_passport(initial)
        return initial

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        if form.instance.pk is None:
            form.instance.created_by = self.request.user
        return super().form_valid(form)

    # Custom methods
    def populate_initial_with_address(self, initial):
        if self.object.doc_type.name == "Address" and not self.object.details:
            initial["details"] = self.object.doc_application.customer.address_bali
        return initial

    def populate_initial_with_passport(self, initial):
        if self.object.doc_type.name == "Passport" and not self.object.file and not self.object.file_link:
            document = self.get_related_passport_document()
            initial = self.update_initial_with_document_data(document, initial)
        return initial

    def get_related_passport_document(self):
        return (
            Document.objects.filter(
                doc_application__customer__pk=self.object.doc_application.customer.pk,
                doc_type__name="Passport",
                completed=True,
            )
            .order_by("-updated_at")
            .first()
        )

    def update_initial_with_document_data(self, document, initial):
        if document:
            self.set_document_warning_message(document)
            if not document.is_expiring and not document.is_expired:
                initial["file"] = document.file
                initial["file_link"] = document.file_link
                initial["doc_number"] = document.doc_number
                initial["expiration_date"] = document.expiration_date
                initial["ocr_check"] = document.ocr_check
                initial["details"] = document.details
                initial["metadata"] = document.metadata
                messages.success(self.request, "Data imported from previous Customer's application")
        return initial

    def set_document_warning_message(self, document):
        if document.is_expiring:
            messages.warning(
                self.request, "We have a previous Passport, but is expiring soon. Please upload a new one."
            )
        elif document.is_expired:
            messages.warning(
                self.request, "We have a previous Passport, but is already expired. Please upload a new one."
            )
