from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from customer_applications.forms import RequiredDocumentUpdateForm
from customer_applications.models import RequiredDocument


class RequiredDocumentUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ("customer_applications.change_requireddocument",)
    model = RequiredDocument
    form_class = RequiredDocumentUpdateForm
    template_name = "customer_applications/requireddocument_update.html"
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
        if self.object.doc_type.name == "Address" and not self.object.details:
            initial["details"] = self.object.doc_application.customer.address_bali

        return initial

    def form_valid(self, form):
        if form.instance.pk is None:
            form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    # if completed is True and all other required documents of the doc_application are uploaded, set the satus of the fisrt doc_application's workflow (the one with task.step = 1) to "completed"
    def save(self, commit=True):
        self.instance = super().save(commit=False)
        if self.instance.completed:
            doc_application = self.instance.doc_application
            if doc_application.all_required_documents_uploaded():
                doc_application.set_status_completed()

    def get_success_url(self):
        return reverse_lazy("customer-application-detail", kwargs={"pk": self.object.doc_application.id})
