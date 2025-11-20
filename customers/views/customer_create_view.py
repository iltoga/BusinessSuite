from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.forms.models import BaseModelForm
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic.edit import CreateView

from core.models.country_code import CountryCode
from customers.forms import CustomerForm
from customers.models import Customer


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

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        mrz_data = self.request.session.get("mrz_data", None)
        if mrz_data and form.is_valid():
            form.instance.names = form.cleaned_data.get("first_name")
            form.instance.surname = form.cleaned_data.get("last_name")
            mrz_data["names"] = form.instance.names
            mrz_data["surname"] = form.instance.surname
            # set the expiry time to 5 minutes from now
            expiry_time = timezone.now() + timezone.timedelta(seconds=300)
            mrz_data["expiry_time"] = expiry_time.timestamp()
            self.request.session["mrz_data"] = mrz_data  # Update session data
            # populate passport fields on the customer instance if present
            try:
                if mrz_data.get("number"):
                    form.instance.passport_number = mrz_data.get("number")
                if mrz_data.get("expiration_date_yyyy_mm_dd"):
                    from datetime import datetime

                    form.instance.passport_expiration_date = datetime.strptime(
                        mrz_data.get("expiration_date_yyyy_mm_dd"), "%Y-%m-%d"
                    ).date()
                if mrz_data.get("issue_date_yyyy_mm_dd"):
                    from datetime import datetime

                    form.instance.passport_issue_date = datetime.strptime(
                        mrz_data.get("issue_date_yyyy_mm_dd"), "%Y-%m-%d"
                    ).date()
            except Exception:
                # If for some reason dates can't be parsed, ignore and continue
                pass
        return super().form_valid(form)

    def form_invalid(self, form: BaseModelForm) -> HttpResponse:
        print(form.errors)
        return super().form_invalid(form)
