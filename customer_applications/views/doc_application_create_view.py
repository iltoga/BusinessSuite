from os import unlink
from typing import Any, Dict

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView

from customer_applications.forms import DocApplicationForm, DocumentCreateFormSet
from customer_applications.models import DocApplication
from customer_applications.models.doc_workflow import DocWorkflow
from customer_applications.models.document import Document
from products.models import DocumentType, Task


class DocApplicationCreateView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ("customer_applications.add_docapplication",)
    model = DocApplication
    form_class = DocApplicationForm
    template_name = "customer_applications/docapplication_create.html"
    success_message = "Customer application created successfully!"
    action_name = "Create"

    def get_success_url(self) -> str:
        return reverse_lazy("customer-application-detail", kwargs={"pk": self.object.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        # get customer_pk from url
        if self.request.POST:
            print(self.request.POST)
            data["documents"] = DocumentCreateFormSet(self.request.POST, prefix="documents")
        else:
            data["documents"] = DocumentCreateFormSet(prefix="documents")
        return data

    def get_initial(self) -> Dict[str, Any]:
        initial = super().get_initial()
        customer_pk = self.kwargs.get("customer_pk", None)
        if customer_pk:
            initial["customer"] = customer_pk
        return initial

    def form_valid(self, form):
        context = self.get_context_data()
        documents = context["documents"]
        form.instance.created_by = self.request.user

        # don't check for documents.is_valid() because it will always be false, since at this point the documents
        # we have some missing fields that will be filled in the next step
        if not documents.is_valid():
            form.add_error(None, "Documents are invalid")
            return super().form_invalid(form)

        with transaction.atomic():
            self.object = form.save()

            document_instances = []
            for document in documents:
                if document.cleaned_data and not document.cleaned_data.get("DELETE"):
                    document.instance.created_by = self.request.user
                    document.instance.doc_application = self.object
                    document.instance.doc_type = document.cleaned_data["doc_type"]
                    document.instance.required = document.cleaned_data["required"]
                    document.instance.created_at = timezone.now()
                    document.instance.updated_at = timezone.now()
                    document_instances.append(document.instance)

            Document.objects.bulk_create(document_instances)  # Use your actual Document model

            # create the first workflow step
            step1 = DocWorkflow()
            step1.start_date = timezone.now()
            step1.task = Task.objects.filter(product=self.object.product, step=1).first()

            if step1.task is None:
                form.add_error(None, "No task associated with this product for step 1")
                return super().form_invalid(form)

            step1.doc_application = self.object
            step1.created_by = self.request.user
            step1.status = DocWorkflow.STATUS_PENDING
            step1.due_date = step1.calculate_workflow_due_date()
            step1.save()

            # create the passport Document if we have the file in the request session
            session_mrz_data = self.request.session.get("mrz_data", None)
            file_path = self.request.session.get("file_path", None)
            file_url = self.request.session.get("file_url", None)
            if session_mrz_data and file_path and file_url:
                # fist check if the customer's name is the same as the name in the passport
                # convert the names to uppercase
                session_mrz_data["names"] = session_mrz_data["names"].upper().strip()
                session_mrz_data["surname"] = session_mrz_data["surname"].upper().strip()
                first_name = self.object.customer.first_name.upper()
                last_name = self.object.customer.last_name.upper()
                if first_name == session_mrz_data["names"] and last_name == session_mrz_data["surname"]:
                    # if the customer's name is the same as the name in the passport, then we can import the file
                    try:
                        with open(file_path, "rb") as f:
                            file = File(f)
                            file_to_delete = file_path
                            doc_model = Document()
                            doc_model.file_link = file_url
                            doc_model.doc_number = session_mrz_data["number"]
                            doc_model.expiration_date = session_mrz_data["expiration_date_yyyy_mm_dd"]
                            doc_model.ocr_check = True
                            doc_model.metadata = session_mrz_data
                            doc_model.completed = True
                            doc_model.doc_application = self.object
                            doc_model.doc_type = DocumentType.objects.get(name="Passport")
                            doc_model.created_by = self.request.user
                            doc_model.created_at = timezone.now()
                            doc_model.updated_at = timezone.now()

                            file_path = default_storage.save(doc_model.get_upload_to(file.name), file)
                            unlink(file_to_delete)
                            doc_model.file = file_path

                            doc_model.save()
                            # Unset the session variables
                            del self.request.session["mrz_data"]
                            del self.request.session["file_path"]
                            del self.request.session["file_url"]
                            messages.success(
                                self.request,
                                "Passport file automatically imported from New Customer. Remember to always check that data are correct.",
                            )
                    except FileNotFoundError:
                        messages.warning(
                            self.request,
                            "Passport file not found in New Customer's session. Please upload it manually.",
                        )

        return super().form_valid(form)
