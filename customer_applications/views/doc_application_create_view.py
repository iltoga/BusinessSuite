import logging
import os
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

# File logger in prod and console in dev
logger = logging.getLogger(__name__)


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

        # check if the session is expired and
        # if the customer_pk in the session is the same as the customer_pk in the form
        session_mrz_data = self.request.session.get("mrz_data", None)
        if session_mrz_data:
            expiry_time_str = session_mrz_data.get("expiry_time", None)
            customer_pk = session_mrz_data.get("customer_pk", None)
            if expiry_time_str and customer_pk:
                expiry_timestamp = float(expiry_time_str)
                if (expiry_timestamp < timezone.now().timestamp()) or (customer_pk != form.instance.customer.pk):
                    self.request.session.pop("mrz_data", None)
                    unlink(self.request.session.pop("file_path", None))
                    self.request.session.pop("file_url", None)

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
                    file_path = self.request.session.get("file_path", None)
                    if file_path and os.path.isfile(file_path) and self.request.session.get("mrz_data", None):
                        continue

                    previous_passport_document = self.get_previous_valid_passport_document(False)
                    if previous_passport_document and os.path.isfile(previous_passport_document.file.path):
                        continue

                document_instances.append(document.instance)

        return document_instances

    def create_workflow_doc_collection_step(self, form):
        # First check if a task exists for step 1 of this product
        task = Task.objects.filter(product=self.object.product, step=1).first()

        if task is None:
            form.add_error(None, "No task associated with this product for step 1")
            return super().form_invalid(form)

        step1 = DocWorkflow()
        step1.start_date = timezone.now()
        step1.task = task
        step1.doc_application = self.object
        step1.created_by = self.request.user
        step1.status = DocWorkflow.STATUS_PENDING
        step1.due_date = step1.calculate_workflow_due_date()
        step1.save()

    def create_passport_document_from_session(self, form) -> bool:
        session_mrz_data = self.request.session.get("mrz_data", None)
        # check if expiry_time is in session and if it is expired.
        # if it is, delete the session data and also delete the file
        if not session_mrz_data:
            return False

        file_path = self.request.session.get("file_path", None)
        file_url = self.request.session.get("file_url", None)
        if session_mrz_data and file_path and file_url:
            if session_mrz_data.get("customer_pk", None) == form.instance.customer.pk:
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
        try:
            file = File(f)
        except FileNotFoundError:
            logger.error("Passport file not found.")
            for key in ["mrz_data", "file_path", "file_url"]:
                self.request.session.pop(key, None)
            return
        except Exception as e:
            logger.error(f"Error opening file. Exception: {str(e)}")
            return

        file_to_delete = file_path
        doc_model = Document(
            file_link=file_url,
            doc_number=session_mrz_data["number"],
            expiration_date=session_mrz_data["expiration_date_yyyy_mm_dd"],
            ocr_check=True,
            metadata=session_mrz_data,
            completed=True,
            doc_application=self.object,
            doc_type=DocumentType.objects.get(name="Passport"),
            created_by=self.request.user,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

        file_path = default_storage.save(Document.get_upload_to(doc_model, file.name), file)
        try:
            unlink(file_to_delete)
        except Exception as e:
            logger.error(f"Error deleting file from temporary storage. Exception: {str(e)}")

        # Delete session variables
        for key in ["mrz_data", "file_path", "file_url"]:
            self.request.session.pop(key, None)

        doc_model.file = file_path

        try:
            doc_model.save()
        except Exception as e:
            messages.error(self.request, f"Error saving document to database. Exception: {str(e)}")
            return

        messages.success(
            self.request,
            "Passport file automatically imported from New Customer. Remember to always check that data are correct.",
        )

    def create_passport_document_from_previous_docapplication(self):
        """
        Create a passport document from the previous docapplication.
        """
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

        try:
            previous_passport_doc = (
                Document.objects.filter(doc_application__customer=customer, doc_type=passport_doc_type)
                .exclude(doc_application=self.object)
                .order_by("-created_at")
                .first()
            )
        except Document.DoesNotExist:
            logger.warning("No previous passport document found.")
            return False

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
