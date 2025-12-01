import logging
import os
from typing import Any, Dict

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView

from core.models.country_code import CountryCode
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

            # Create passport document from customer's stored data or previous application
            # Only process if Passport DocumentType exists and is required by the product
            if self.should_process_passport_document():
                # Try customer's stored passport first, then previous application
                if not self.create_passport_document_from_customer():
                    self.create_passport_document_from_previous_docapplication()

        # Add success message
        messages.success(self.request, self.success_message)
        # Redirect to the success URL
        return HttpResponseRedirect(self.get_success_url())

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
                    # Check if customer has passport file stored
                    customer = self.object.customer
                    if customer.passport_file and customer.passport_number:
                        if default_storage.exists(customer.passport_file.name):
                            continue

                    # Check for previous passport document
                    previous_passport_document = self.get_previous_valid_passport_document(False)
                    if previous_passport_document and previous_passport_document.file:
                        try:
                            if os.path.isfile(previous_passport_document.file.path):
                                continue
                        except Exception:
                            pass

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

    def should_process_passport_document(self) -> bool:
        """
        Check if passport document should be processed.
        Returns True if Passport DocumentType exists and is required by the product.
        """
        try:
            passport_doc_type = DocumentType.objects.get(name="Passport")
            # Check if this document type is required by the product
            required_docs = self.object.product.required_documents or ""
            required_doc_names = [doc.strip() for doc in required_docs.split(",") if doc.strip()]
            return passport_doc_type.name in required_doc_names
        except DocumentType.DoesNotExist:
            return False

    def _get_passport_data_from_customer(self, customer):
        """
        Get passport data prioritizing Customer model fields over passport_metadata.
        Returns a dict with passport data fields.
        """
        metadata = customer.passport_metadata or {}

        # Helper to get value from customer field first, then metadata
        def get_value(customer_field, metadata_key):
            customer_value = getattr(customer, customer_field, None)
            if customer_value:
                return customer_value
            return metadata.get(metadata_key)

        # Parse date from metadata if needed
        def parse_date(date_value):
            if date_value is None:
                return None
            if hasattr(date_value, "year"):  # Already a date object
                return date_value
            # Try to parse string date
            from datetime import datetime

            try:
                return datetime.strptime(str(date_value), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return None

        return {
            "doc_number": get_value("passport_number", "number"),
            "expiration_date": parse_date(get_value("passport_expiration_date", "expiration_date_yyyy_mm_dd")),
            "issue_date": parse_date(get_value("passport_issue_date", "issue_date_yyyy_mm_dd")),
            "nationality": customer.nationality.alpha3_code if customer.nationality else metadata.get("nationality"),
            "birth_place": get_value("birth_place", "birth_place"),
            "birthdate": parse_date(get_value("birthdate", "date_of_birth_yyyy_mm_dd")),
            "issuing_authority": metadata.get("issuing_authority"),
        }

    def create_passport_document_from_customer(self) -> bool:
        """
        Create a passport document from the customer's stored passport file and data.
        Prioritizes Customer model fields over passport_metadata.
        Returns True if successful, False otherwise.
        """
        customer = self.object.customer

        # Check if customer has passport file and passport number
        if not customer.passport_file or not customer.passport_number:
            return False

        try:
            passport_doc_type = DocumentType.objects.get(name="Passport")
        except DocumentType.DoesNotExist:
            logger.warning("Passport DocumentType does not exist. Skipping passport document creation.")
            return False

        try:
            # Get passport data prioritizing Customer fields over metadata
            passport_data = self._get_passport_data_from_customer(customer)

            # Build a trimmed metadata dict from the customer fields and a few useful MRZ/AI fields
            trimmed_metadata = {}

            # MRZ/AI metadata saved on the customer (if any)
            mrz_meta = customer.passport_metadata or {}

            # Helper to format dates as YYYY-MM-DD
            def fmt_date(d):
                if not d:
                    return None
                # If already a date
                if hasattr(d, "isoformat"):
                    return d.isoformat()
                # Try to parse a string and reformat
                try:
                    from datetime import datetime

                    return datetime.strptime(str(d), "%Y-%m-%d").date().isoformat()
                except Exception:
                    return str(d)

            # Include customer passport fields
            trimmed_metadata["number"] = passport_data.get("doc_number")
            trimmed_metadata["issue_date_yyyy_mm_dd"] = fmt_date(passport_data.get("issue_date"))
            trimmed_metadata["expiration_date_yyyy_mm_dd"] = fmt_date(passport_data.get("expiration_date"))
            trimmed_metadata["date_of_birth_yyyy_mm_dd"] = fmt_date(passport_data.get("birthdate"))
            trimmed_metadata["birth_place"] = passport_data.get("birth_place")
            # nationality: prefer customer nationality alpha3 code then try mrz metadata
            alpha3 = passport_data.get("nationality") or mrz_meta.get("nationality")
            country_obj = CountryCode.objects.get_country_code_by_alpha3_code(alpha3) if alpha3 else None
            country_name = country_obj.country if country_obj else alpha3
            trimmed_metadata["nationality"] = country_name
            # country will be derived below (prefer MRZ issuing country or nationality name)
            # Additional fields requested: sex, country, eye_color, height_cm
            # Prefer Customer.gender and fallback to MRZ/AI metadata if present
            trimmed_metadata["sex"] = customer.gender or mrz_meta.get("sex") or mrz_meta.get("mrz_sex")
            trimmed_metadata["country"] = (
                mrz_meta.get("country") or mrz_meta.get("issuing_country") or trimmed_metadata.get("nationality")
            )
            trimmed_metadata["eye_color"] = mrz_meta.get("eye_color")
            trimmed_metadata["height_cm"] = mrz_meta.get("height_cm")
            trimmed_metadata["issuing_authority"] = passport_data.get("issuing_authority") or mrz_meta.get(
                "issuing_authority"
            )

            # Build details string from available data
            details_parts = []
            if passport_data.get("birth_place"):
                details_parts.append(f"Birth Place: {passport_data['birth_place']}")
            if passport_data.get("birthdate"):
                details_parts.append(f"Birthdate: {passport_data['birthdate']}")
            if passport_data.get("nationality"):
                details_parts.append(f"Nationality: {country_name}")
            if passport_data.get("issue_date"):
                details_parts.append(f"Issue Date: {passport_data['issue_date']}")

            # Create the document from customer's stored passport data
            doc_model = Document(
                doc_number=passport_data["doc_number"],
                expiration_date=passport_data["expiration_date"],
                details="\n".join(details_parts) if details_parts else "",
                ocr_check=bool(customer.passport_metadata),
                metadata=trimmed_metadata,
                completed=True,
                doc_application=self.object,
                doc_type=passport_doc_type,
                created_by=self.request.user,
                created_at=timezone.now(),
                updated_at=timezone.now(),
            )

            # Copy the passport file from customer to the document
            if customer.passport_file and default_storage.exists(customer.passport_file.name):
                with customer.passport_file.open("rb") as f:
                    file = File(f)
                    file_name = os.path.basename(customer.passport_file.name)
                    # Use Document's get_upload_to to generate the proper path
                    from customer_applications.models.document import get_upload_to

                    upload_path = get_upload_to(doc_model, file_name)
                    saved_path = default_storage.save(upload_path, file)
                    doc_model.file = saved_path
                    doc_model.file_link = default_storage.url(saved_path)

            doc_model.save()

            messages.success(
                self.request,
                "Passport file automatically imported from Customer profile. Remember to always check that data are correct.",
            )
            return True

        except Exception as e:
            logger.error(f"Error creating passport document from customer: {e}")
            return False

    def create_passport_document_from_previous_docapplication(self):
        """
        Create a passport document from the previous docapplication.
        """
        try:
            doc_type = DocumentType.objects.get(name="Passport")
        except DocumentType.DoesNotExist:
            logger.warning("Passport DocumentType does not exist. Skipping passport document creation.")
            return

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
        try:
            passport_doc_type = DocumentType.objects.get(name="Passport")
        except DocumentType.DoesNotExist:
            logger.warning("Passport DocumentType does not exist.")
            return False

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
