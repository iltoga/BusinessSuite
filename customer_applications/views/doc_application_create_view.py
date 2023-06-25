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
        if self.request.POST:
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
        # Get context data to provide the formsets for our view
        context = self.get_context_data()
        # Get the documents formset from the context
        documents = context["documents"]
        # Assign the currently logged in user as the creator of the form instance
        form.instance.created_by = self.request.user

        # Check if all the documents in the formset are valid
        if not documents.is_valid():
            # Add a form error if the documents formset is invalid
            form.add_error(None, "Documents are invalid")
            # Return the form invalid function from the parent class
            return super().form_invalid(form)

        # Ensure all operations inside are atomic, meaning that if any operation fails,
        # all operations are rolled back to maintain database consistency
        with transaction.atomic():
            # Save the form and assign the instance to self.object
            self.object = form.save()

            # Prepare document instances for bulk creation
            document_instances = self.prepare_document_instances(documents)
            Document.objects.bulk_create(document_instances)

            # Create the first workflow step, which is a document collection step
            self.create_workflow_doc_collection_step(form)

            # Check if there is a passport file in the session and create a passport document if there is
            if not self.create_passport_document_from_session(form):
                # Try to create a passport document from the previous application if there is one
                self.create_passport_document_from_previous_docapplication()

        # Call the form_valid function of the parent class to finish processing
        return super().form_valid(form)

    def prepare_document_instances(self, documents):
        document_instances = []
        for document in documents:
            if document.cleaned_data and not document.cleaned_data.get("DELETE"):
                document.instance.created_by = self.request.user
                document.instance.doc_application = self.object
                document.instance.doc_type = document.cleaned_data["doc_type"]
                document.instance.required = document.cleaned_data["required"]
                document.instance.created_at = timezone.now()
                document.instance.updated_at = timezone.now()

                if document.instance.doc_type.name == "Passport":
                    if (
                        self.request.session.get("file_path", None) and self.request.session.get("mrz_data", None)
                    ) or self.get_previous_valid_passport_document(False):
                        continue

                document_instances.append(document.instance)

        return document_instances

    def create_workflow_doc_collection_step(self, form):
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

    def create_passport_document_from_session(self, form) -> bool:
        session_mrz_data = self.request.session.get("mrz_data", None)
        file_path = self.request.session.get("file_path", None)
        file_url = self.request.session.get("file_url", None)
        if session_mrz_data and file_path and file_url:
            # Convert the names to uppercase
            session_mrz_data["names"] = session_mrz_data["names"].upper().strip()
            session_mrz_data["surname"] = session_mrz_data["surname"].upper().strip()
            first_name = self.object.customer.first_name.upper()
            last_name = self.object.customer.last_name.upper()
            if first_name == session_mrz_data["names"] and last_name == session_mrz_data["surname"]:
                try:
                    with open(file_path, "rb") as f:
                        self.import_passport_file(session_mrz_data, file_path, file_url, f)
                except FileNotFoundError:
                    messages.warning(
                        self.request,
                        "Passport file not found in New Customer's session. Please upload it manually.",
                    )
            return True
        return False

    def import_passport_file(self, session_mrz_data, file_path, file_url, f):
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

        del self.request.session["mrz_data"]
        del self.request.session["file_path"]
        del self.request.session["file_url"]
        messages.success(
            self.request,
            "Passport file automatically imported from New Customer. Remember to always check that data are correct.",
        )

    def create_passport_document_from_previous_docapplication(self):
        """
        Create a passport document from the previous docapplication.
        """
        customer = self.object.customer
        doc_type = DocumentType.objects.get(name="Passport")
        previous_passport_doc = self.get_previous_valid_passport_document()
        if previous_passport_doc:
            new_passport_doc = Document()
            new_passport_doc.doc_application = self.object
            new_passport_doc.doc_type = doc_type
            new_passport_doc.file = previous_passport_doc.file
            new_passport_doc.file_link = previous_passport_doc.file_link
            new_passport_doc.doc_number = previous_passport_doc.doc_number
            new_passport_doc.expiration_date = previous_passport_doc.expiration_date
            new_passport_doc.ocr_check = previous_passport_doc.ocr_check
            new_passport_doc.metadata = previous_passport_doc.metadata
            new_passport_doc.completed = previous_passport_doc.completed
            new_passport_doc.required = previous_passport_doc.required
            new_passport_doc.created_by = self.request.user
            new_passport_doc.created_at = timezone.now()
            new_passport_doc.updated_at = timezone.now()
            new_passport_doc.save()
            messages.success(
                self.request,
                "Passport file automatically imported from previous Customer's Application. Remember to always check that data are correct.",
            )

    def get_previous_valid_passport_document(self, with_messages=True):
        customer = self.object.customer
        passport_doc_type = DocumentType.objects.get(name="Passport")
        previous_passport_doc = (
            Document.objects.filter(doc_application__customer=customer, doc_type=passport_doc_type)
            .exclude(doc_application=self.object)
            .order_by("-created_at")
            .first()
        )
        if previous_passport_doc:
            if previous_passport_doc.is_expired:
                if with_messages:
                    messages.warning(
                        self.request,
                        "The passport of the previous Customer's Application is expired. Please upload a new one.",
                    )
                return False
            if previous_passport_doc.is_expiring:
                if with_messages:
                    messages.warning(
                        self.request,
                        "The passport of the previous Customer's Application is expiring. Please upload a new one.",
                    )
                return False
            return previous_passport_doc
        return False
