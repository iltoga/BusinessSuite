from typing import Any, Dict, Optional

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core import serializers
from django.db import models, transaction
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

import customer_applications
from customer_applications.models import DocApplication
from customers.models import Customer
from invoices.forms import (
    BaseInvoiceApplicationFormSet,
    InvoiceApplicationCreateForm,
    InvoiceApplicationUpdateForm,
    InvoiceCreateForm,
    InvoiceUpdateForm,
)
from invoices.models import Invoice
from invoices.models.invoice import InvoiceApplication

InvoiceApplicationCreateFormSet = inlineformset_factory(
    Invoice,
    InvoiceApplication,
    form=InvoiceApplicationCreateForm,
    formset=BaseInvoiceApplicationFormSet,
    extra=1,
    can_delete=True,
)

InvoiceApplicationUpdateFormSet = inlineformset_factory(
    Invoice,
    InvoiceApplication,
    form=InvoiceApplicationUpdateForm,
    formset=BaseInvoiceApplicationFormSet,
    extra=0,
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
    form_class = InvoiceCreateForm
    template_name = "invoices/invoice_create.html"
    success_url = reverse_lazy("invoice-list")  # URL pattern name for the invoice list view
    success_message = "Invoice created successfully!"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)

        customer_applications = DocApplication.objects.none()
        selected_customer_application = self.get_customer_application_from_kwargs()
        if selected_customer_application:
            customer = selected_customer_application.customer
        else:
            customer = self.get_customer_from_kwargs()
        if customer:
            # TODO: not sure about this. double check it
            data["customer"] = serializers.serialize("json", [])

            data["customer_applications_json"] = customer.doc_applications_to_json()
            data["selected_customer_application_pk"] = (
                selected_customer_application.pk if selected_customer_application else ""
            )

            # Avoid adding already invoiced applications when creating a new invoice
            customer_applications = customer.get_doc_applications_for_invoice()
            # TODO: find a better place to put this message
            if not customer_applications:
                messages.error(
                    self.request, "No applications found for this customer! Did you complete the document collection?"
                )
        else:
            data["customer_applications_json"] = serializers.serialize("json", [])

        if self.request.POST:
            data["invoice_applications"] = InvoiceApplicationCreateFormSet(
                self.request.POST,
                form_kwargs={"customer_applications": customer_applications},
            )
        else:
            formset = InvoiceApplicationCreateFormSet(
                form_kwargs={
                    "customer_applications": customer_applications,
                    "selected_customer_application": selected_customer_application,
                }
            )
            data["invoice_applications"] = formset

        # get currency settings
        data["currency"] = settings.CURRENCY
        data["currency_symbol"] = settings.CURRENCY_SYMBOL
        data["currency_decimal_places"] = settings.CURRENCY_DECIMAL_PLACES
        return data

    def get_initial(self):
        initial = super().get_initial()
        customer_application = self.get_customer_application_from_kwargs()
        if customer_application:
            customer = customer_application.customer
            initial["selected_customer_application"] = customer_application
        else:
            customer = self.get_customer_from_kwargs()
        if customer:
            initial["customer"] = customer
        return initial

    @transaction.atomic
    def form_valid(self, form):
        context = self.get_context_data()
        invoice_applications = context["invoice_applications"]

        form.instance.created_by = self.request.user
        self.object = form.save(commit=False)

        if all(form.is_valid() for form in invoice_applications) and invoice_applications.is_valid():
            self.object.save()  # Save the Invoice after checking InvoiceApplications
            invoice_applications.instance = self.object
            invoice_applications.save()
        else:
            return self.form_invalid(form)

        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below and resubmit.")
        return super().form_invalid(form)

    # Custom methods

    def get_customer_from_kwargs(self):
        customer_id = self.kwargs.get("customer_id", None)
        if customer_id:
            try:
                return Customer.objects.get(pk=customer_id)
            except Customer.DoesNotExist:
                messages.error(self.request, "Customer not found!")
        return None

    def get_customer_application_from_kwargs(self):
        doc_application_pk = self.kwargs.get("doc_application_pk", None)
        if doc_application_pk:
            try:
                return DocApplication.objects.get(pk=doc_application_pk)
            except DocApplication.DoesNotExist:
                messages.error(self.request, "Customer application not found!")
        return None


class InvoiceUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ("invoices.change_invoice",)
    model = Invoice
    form_class = InvoiceUpdateForm
    template_name = "invoices/invoice_update.html"
    success_url = reverse_lazy("invoice-list")  # URL pattern name for the invoice list view
    success_message = "Invoice updated successfully!"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)

        customer = self.object.customer
        customer_applications = customer.get_doc_applications_for_invoice(current_invoice_to_include=self.object)

        data["customer_applications_json"] = customer.doc_applications_to_json(current_invoice_to_include=self.object)

        if self.request.POST:
            # can I add the missing data (such as the ones not being posted because the field was disabled) to the POST request?
            data["invoice_applications"] = InvoiceApplicationUpdateFormSet(
                self.request.POST,
                instance=self.object,
                prefix="invoice_applications",
                form_kwargs={"customer_applications": customer_applications},
            )
        else:
            data["invoice_applications"] = InvoiceApplicationUpdateFormSet(
                instance=self.object,
                prefix="invoice_applications",
                form_kwargs={"customer_applications": customer_applications},
            )

        # get currency settings
        data["currency"] = settings.CURRENCY
        data["currency_symbol"] = settings.CURRENCY_SYMBOL
        data["currency_decimal_places"] = settings.CURRENCY_DECIMAL_PLACES
        return data

    @transaction.atomic
    def form_valid(self, form):
        context = self.get_context_data()
        invoice_applications = context["invoice_applications"]
        form.instance.updated_by = self.request.user

        if all(form.is_valid() for form in invoice_applications) and invoice_applications.is_valid():
            self.object = form.save()  # Save the Invoice after checking InvoiceApplications
            invoice_applications.instance = self.object
            invoice_applications.save()
        else:
            return self.form_invalid(form)

        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below and resubmit.")
        return super().form_invalid(form)


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

    def get_object(self):
        """
        Returns the object the view is displaying.
        It can be used to call the same view with different arguments of the same type (eg. int:pk and int:doc_application_pk).
        """
        doc_application_pk = self.kwargs.get("doc_application_pk", None)
        if doc_application_pk:
            invoice = get_object_or_404(Invoice, invoice_applications__customer_application__pk=doc_application_pk)
            return invoice
        else:
            return super().get_object()

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["invoice_applications"] = self.object.invoice_applications.all()
        return data
