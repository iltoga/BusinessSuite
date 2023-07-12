from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core import serializers
from django.db import transaction
from django.forms import inlineformset_factory
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

import customer_applications
from customer_applications.models import DocApplication
from customers.models import Customer
from invoices.forms import BaseInvoiceApplicationFormSet, InvoiceApplicationForm, InvoiceForm
from invoices.models import Invoice
from invoices.models.invoice import InvoiceApplication

InvoiceApplicationFormSet = inlineformset_factory(
    Invoice,
    InvoiceApplication,
    form=InvoiceApplicationForm,
    formset=BaseInvoiceApplicationFormSet,
    extra=1,
    can_delete=True,
)


class InvoiceListView(PermissionRequiredMixin, ListView):
    permission_required = ("invoices.view_invoice",)
    model = Invoice
    template_name = "invoices/invoice_list.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q")
        if query and self.model is not None:
            order_by = self.model._meta.ordering
            queryset = self.model.objects.search_customers(query).order_by(*order_by)
        return queryset


class InvoiceCreateView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ("invoices.add_invoice",)
    model = Invoice
    form_class = InvoiceForm
    template_name = "invoices/invoice_create.html"
    success_url = reverse_lazy("invoice-list")  # URL pattern name for the invoice list view
    success_message = "Invoice created successfully!"

    def get_customer(self):
        customer_id = self.kwargs.get("customer_id", None)
        if customer_id:
            try:
                return Customer.objects.get(pk=customer_id)
            except Customer.DoesNotExist:
                messages.error(self.request, "Customer not found!")
        return None

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)

        customer = self.get_customer()
        customer_applications = DocApplication.objects.none()
        if customer:
            data["customer"] = serializers.serialize("json", [])
            customer_applications = DocApplication.objects.filter(
                customer=customer
            ).filter_by_document_collection_completed()
            # TODO: find a better place to put this message
            if not customer_applications:
                messages.error(
                    self.request, "No applications found for this customer! Did you complete the document collection?"
                )
        data["customer_applications_json"] = serializers.serialize("json", customer_applications)

        if self.request.POST:
            data["invoice_applications"] = InvoiceApplicationFormSet(
                self.request.POST,
                form_kwargs={"customer_applications": customer_applications},
            )
        else:
            formset = InvoiceApplicationFormSet(form_kwargs={"customer_applications": customer_applications})
            data["invoice_applications"] = formset

        # get currency settings
        data["currency"] = settings.CURRENCY
        data["currency_symbol"] = settings.CURRENCY_SYMBOL
        data["currency_decimal_places"] = settings.CURRENCY_DECIMAL_PLACES
        return data

    def get_initial(self):
        initial = super().get_initial()
        customer = self.get_customer()
        if customer:
            initial["customer"] = customer
        return initial

    @transaction.atomic
    def form_valid(self, form):
        context = self.get_context_data()
        invoice_applications = context["invoice_applications"]

        self.object = form.save(commit=False)

        if all(form.is_valid() for form in invoice_applications) and invoice_applications.is_valid():
            self.object.save()  # Save the Invoice after checking InvoiceApplications
            invoice_applications.instance = self.object
            invoice_applications.save()
        else:
            return self.form_invalid(form)

        return super().form_valid(form)

    def form_invalid(self, form):
        print(form.errors)  # Check the form errors in console
        messages.error(self.request, "Please correct the errors below and resubmit.")
        return super().form_invalid(form)


class InvoiceUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ("invoices.change_invoice",)
    model = Invoice
    form_class = InvoiceForm
    template_name = "invoices/invoice_update.html"
    success_url = reverse_lazy("invoice-list")  # URL pattern name for the invoice list view
    success_message = "Invoice updated successfully!"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data["invoice_applications"] = InvoiceApplicationFormSet(self.request.POST, instance=self.object)
        else:
            data["invoice_applications"] = InvoiceApplicationFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        invoice_applications = context["invoice_applications"]

        self.object = form.save()
        if invoice_applications.is_valid():
            invoice_applications.instance = self.object
            invoice_applications.save()

        return super().form_valid(form)


class InvoiceDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = ("invoices.delete_invoice",)
    model = Invoice
    template_name = "invoices/invoice_delete.html"
    success_url = reverse_lazy("invoice-list")  # URL pattern name for the invoice list view

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Add any extra steps here before deleting
        return super().delete(request, *args, **kwargs)


class InvoiceDetailView(PermissionRequiredMixin, DetailView):
    permission_required = ("invoices.view_invoice",)
    model = Invoice
    template_name = "invoices/invoice_detail.html"
