from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import UpdateView

from customer_applications.forms import DocApplicationForm, NewDocumentFormSet
from customer_applications.models import DocApplication


class DocApplicationUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ("customer_applications.change_docapplication",)
    model = DocApplication
    form_class = DocApplicationForm
    template_name = "customer_applications/docapplication_update.html"
    success_url = reverse_lazy("customer-application-list")
    success_message = "Customer application updated successfully!"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            # New documents formset (for adding new documents)
            data["new_documents"] = NewDocumentFormSet(self.request.POST, instance=self.object, prefix="new_documents")
        else:
            data["new_documents"] = NewDocumentFormSet(instance=self.object, prefix="new_documents")
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        new_documents = context["new_documents"]
        form.instance.updated_by = self.request.user

        # Check if all new documents in the formset are valid
        if not new_documents.is_valid():
            form.add_error(None, "New documents are invalid")
            return super().form_invalid(form)

        with transaction.atomic():
            self.object = form.save()

            # Save new documents
            for new_doc_form in new_documents:
                if new_doc_form.cleaned_data and not new_doc_form.cleaned_data.get("DELETE"):
                    new_doc_form.instance.created_by = self.request.user
                    new_doc_form.instance.doc_application = self.object
                    new_doc_form.instance.doc_type = new_doc_form.cleaned_data["doc_type"]
                    new_doc_form.instance.required = new_doc_form.cleaned_data["required"]
                    new_doc_form.instance.created_at = timezone.now()
                    new_doc_form.instance.updated_at = timezone.now()
                    new_doc_form.instance.save()

        return super().form_valid(form)
