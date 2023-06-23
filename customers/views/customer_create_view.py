from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView

from customers.forms import CustomerForm
from customers.models import Customer


class CustomerCreateView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ("customers.add_customer",)
    model = Customer
    form_class = CustomerForm
    template_name = "customers/customer_form.html"
    success_url = reverse_lazy("customer-list")
    success_message = "Customer added successfully!"

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
            self.request.session["mrz_data"] = mrz_data  # Update session data
        return super().form_valid(form)
