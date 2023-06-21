from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from customer_applications.forms import DocApplicationForm, DocumentUpdateFormSet
from customer_applications.models import DocApplication


class DocApplicationUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ("customer_applications.change_docapplication",)
    model = DocApplication
    form_class = DocApplicationForm
    template_name = "customer_applications/docapplication_update.html"
    success_url = reverse_lazy("customer-application-list")
    success_message = "Customer application created successfully!"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data["documents"] = DocumentUpdateFormSet(self.request.POST, instance=self.object, prefix="documents")
        else:
            data["documents"] = DocumentUpdateFormSet(instance=self.object, prefix="documents")
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        documents = context["documents"]
        form.instance.updated_by = self.request.user
        with transaction.atomic():
            self.object = form.save(commit=False)  # Don't save it yet
            if documents.is_valid():
                documents.instance = self.object
                documents.save(commit=False)
                for document in documents:
                    document.instance.updated_by = self.request.user
                    if document.cleaned_data and not document.cleaned_data.get("DELETE"):
                        if "file" in document.files:
                            document.instance.file = document.files["file"]
                        if "metadata" in document.cleaned_data:
                            document.instance.metadata = document.cleaned_data["metadata"]
                        document.instance.save()
                self.object.save()  # Now save the form

        return super().form_valid(form)
