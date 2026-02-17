import logging
import os

from django.conf import settings
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.files import File
from django.core.files.storage import default_storage
from django.forms.models import BaseModelForm
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic.edit import CreateView

from core.models.country_code import CountryCode
from core.services.logger_service import Logger
from customers.forms import CustomerForm
from customers.models import Customer, get_passport_upload_to

logger = Logger.get_logger(__name__)


class CustomerCreateView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ("customers.add_customer",)
    model = Customer
    form_class = CustomerForm
    template_name = "customers/customer_form.html"
    success_message = "Customer added successfully!"

    def get_success_url(self):
        mrz_data = self.request.session.get("mrz_data", None)
        if mrz_data:
            # Add the customer pk to the session data so that we can match it against
            # the customer.pk of the customer when creating a customer application
            mrz_data["customer_pk"] = self.object.pk
            self.request.session["mrz_data"] = mrz_data
        return reverse_lazy("customer-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action_name"] = "Create"
        return context

    def get_initial(self):
        initial = super().get_initial()
        # Set default email if not provided
        if not initial.get("email"):
            initial["email"] = getattr(settings, "DEFAULT_CUSTOMER_EMAIL", None)
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        mrz_data = self.request.session.get("mrz_data", None)
        file_storage_path = self.request.session.get("file_path", None)

        if mrz_data and form.is_valid():
            form.instance.names = form.cleaned_data.get("first_name")
            form.instance.surname = form.cleaned_data.get("last_name")
            mrz_data["names"] = form.instance.names
            mrz_data["surname"] = form.instance.surname
            # set the expiry time to 5 minutes from now
            expiry_time = timezone.now() + timezone.timedelta(seconds=300)
            mrz_data["expiry_time"] = expiry_time.timestamp()
            self.request.session["mrz_data"] = mrz_data  # Update session data
            # populate passport fields on the customer instance ONLY if form field is empty
            # This allows user-edited values to take precedence over MRZ session data
            try:
                if mrz_data.get("number") and not form.cleaned_data.get("passport_number"):
                    form.instance.passport_number = mrz_data.get("number")
                if mrz_data.get("expiration_date_yyyy_mm_dd") and not form.cleaned_data.get("passport_expiration_date"):
                    from datetime import datetime

                    form.instance.passport_expiration_date = datetime.strptime(
                        mrz_data.get("expiration_date_yyyy_mm_dd"), "%Y-%m-%d"
                    ).date()
                if mrz_data.get("issue_date_yyyy_mm_dd") and not form.cleaned_data.get("passport_issue_date"):
                    from datetime import datetime

                    form.instance.passport_issue_date = datetime.strptime(
                        mrz_data.get("issue_date_yyyy_mm_dd"), "%Y-%m-%d"
                    ).date()

                # Store passport metadata from MRZ/AI extraction
                form.instance.passport_metadata = mrz_data
                logger.info(f"Set passport_metadata on customer: {mrz_data.get('number')}")
            except Exception as e:
                # If for some reason dates can't be parsed, log and continue
                logger.error(f"Error parsing passport data: {e}")

        # Call parent's form_valid to save the customer instance first
        response = super().form_valid(form)

        # After saving customer, copy passport file from session temp location to customer folder
        # Only if passport number is populated (at least passport number requirement)
        # Use self.object which is the saved instance
        source_file_exists = self._source_file_exists(file_storage_path)
        if self.object.passport_number and source_file_exists:
            try:
                self._save_passport_file_to_customer(self.object, file_storage_path)
                # Clear session data after successful save
                for key in ["mrz_data", "file_path", "file_url"]:
                    self.request.session.pop(key, None)
            except Exception as e:
                logger.error(f"Error saving passport file to customer: {e}")
        else:
            logger.warning(
                f"Passport file not saved. passport_number={self.object.passport_number}, "
                f"file_path={file_storage_path}, "
                f"exists={source_file_exists}"
            )

        return response

    def _source_file_exists(self, source_file_path):
        if not source_file_path:
            return False
        if os.path.isabs(source_file_path):
            return os.path.isfile(source_file_path)
        try:
            return default_storage.exists(source_file_path)
        except Exception:
            return False

    def _save_passport_file_to_customer(self, customer, source_file_path):
        """
        Copy the passport file from session temp storage location to the customer's folder.
        """
        try:
            if os.path.isabs(source_file_path):
                source_handle = open(source_file_path, "rb")
            else:
                source_handle = default_storage.open(source_file_path, "rb")

            with source_handle as f:
                file = File(f)
                # Generate the upload path
                filename = os.path.basename(source_file_path)
                upload_path = get_passport_upload_to(customer, filename)

                # Save the file to default storage
                saved_path = default_storage.save(upload_path, file)

                # Update the customer's passport_file field
                customer.passport_file = saved_path
                customer.save(update_fields=["passport_file"])

                logger.info(f"Passport file saved to customer {customer.pk}: {saved_path}")
        except FileNotFoundError:
            logger.error(f"Passport file not found at: {source_file_path}")
        except Exception as e:
            logger.error(f"Error saving passport file: {e}")

    def form_invalid(self, form: BaseModelForm) -> HttpResponse:
        return super().form_invalid(form)
