import re
from typing import Any, Optional
from xml.dom import ValidationErr

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import models
from django.forms import ValidationError
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from customers.models import Customer
from invoices.models.invoice import InvoiceApplication
from payments.forms import PaymentForm
from payments.models import Payment


class CreatePaymentView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = "payments/payment_form.html"
    permission_required = "payments.add_payment"
    success_message = "Payment was created successfully"

    def get_success_url(self):
        return reverse_lazy("payment-detail", kwargs={"pk": self.object.pk})

    def post(self, request, *args, **kwargs):
        # add the invoice application pk to the session so that it can be used in the next view (payment detail) to redirect to the invoice application detail
        invoice_application_pk = self.kwargs.get("invoice_application_pk", None)
        if invoice_application_pk:
            request.session["invoice_application_pk"] = invoice_application_pk

        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Payment"
        context["action_name"] = "Create"
        invoice_application_pk = self.kwargs.get("invoice_application_pk", None)
        if invoice_application_pk:
            invoice_application = InvoiceApplication.objects.filter(pk=invoice_application_pk).not_fully_paid().first()
            if not invoice_application:
                raise ValidationErr("Invoice Application does not exist or is fully paid.")
            context["invoice_application"] = invoice_application

        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)

        customer_pk = self.kwargs.get("customer_pk", None)
        invoice_application_pk = self.kwargs.get("invoice_application_pk", None)
        if customer_pk:
            # Optimize: select_related to avoid N+1 queries
            invoice_applications = (
                InvoiceApplication.objects.filter(invoice__customer=customer_pk)
                .not_fully_paid()
                .select_related("customer_application__product", "customer_application__customer", "invoice")
            )
            if not invoice_applications.exists():
                raise ValidationError("Invoice Application does not exist or is fully paid.")
            form.fields["invoice_application"].queryset = invoice_applications
        elif invoice_application_pk:
            invoice_application = (
                InvoiceApplication.objects.filter(pk=invoice_application_pk)
                .not_fully_paid()
                .select_related("customer_application__product", "customer_application__customer", "invoice__customer")
                .first()
            )
            if not invoice_application:
                raise ValidationError("Invoice Application does not exist or is fully paid.")
            form.fields["invoice_application"].queryset = InvoiceApplication.objects.filter(pk=invoice_application_pk)
            form.fields["from_customer"].queryset = Customer.objects.filter(pk=invoice_application.invoice.customer.pk)
        else:
            # Optimize: use only() to load minimal fields, preventing loading all customer data
            form.fields["invoice_application"].queryset = InvoiceApplication.objects.not_fully_paid().select_related(
                "customer_application__product", "customer_application__customer", "invoice"
            )
            form.fields["from_customer"].queryset = (
                Customer.objects.filter(active=True)
                .only("id", "first_name", "last_name", "company_name", "customer_type")
                .order_by("first_name", "last_name")
            )
        return form

    def get_initial(self):
        initial = super().get_initial()
        invoice_application_pk = self.kwargs.get("invoice_application_pk")
        customer_pk = self.kwargs.get("customer_pk")

        if invoice_application_pk:
            invoice_application = InvoiceApplication.objects.filter(pk=invoice_application_pk).first()
            if invoice_application:
                initial["invoice_application"] = invoice_application
                initial["from_customer"] = invoice_application.invoice.customer
                initial["amount"] = invoice_application.due_amount

        if customer_pk:
            customer = Customer.objects.filter(pk=customer_pk).first()
            if customer:
                initial["from_customer"] = customer

        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Payment was not created because of errors in the data.")
        return super().form_invalid(form)


class UpdatePaymentView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Payment
    form_class = PaymentForm
    template_name = "payments/payment_form.html"
    permission_required = "payments.change_payment"
    success_message = "Payment was updated successfully"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Optimize: limit querysets to only necessary data
        if self.object and self.object.pk:
            # When updating, limit to current payment's invoice application and customer
            form.fields["invoice_application"].queryset = InvoiceApplication.objects.filter(
                pk=self.object.invoice_application.pk
            ).select_related("customer_application__product", "customer_application__customer", "invoice")
            form.fields["from_customer"].queryset = Customer.objects.filter(pk=self.object.from_customer.pk)
        else:
            # Fallback: optimize with select_related and only()
            form.fields["invoice_application"].queryset = InvoiceApplication.objects.not_fully_paid().select_related(
                "customer_application__product", "customer_application__customer", "invoice"
            )
            form.fields["from_customer"].queryset = Customer.objects.filter(active=True).only(
                "id", "first_name", "last_name", "company_name", "customer_type"
            )
        return form

    def get_success_url(self):
        return reverse_lazy("payment-detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Update Payment"
        context["action_name"] = "Update"
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Payment was not updated becaue of errors in the data.")
        return super().form_invalid(form)


class DeletePaymentView(PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Payment
    template_name = "payments/payment_delete.html"
    permission_required = "payments.delete_payment"
    success_message = "Payment was deleted successfully"

    def get_success_url(self):
        return reverse_lazy("payment-list")

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, self.success_message)
        return super().delete(request, *args, **kwargs)


class PaymentDetailView(PermissionRequiredMixin, DetailView):
    model = Payment
    template_name = "payments/payment_detail.html"
    permission_required = "payments.view_payment"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Payment Details"
        invoice_application_pk = self.request.session.get("invoice_application_pk", None)
        if invoice_application_pk:
            del self.request.session["invoice_application_pk"]
            invoice_application = InvoiceApplication.objects.filter(pk=invoice_application_pk).first()
            if not invoice_application:
                raise ValidationError("Invoice Application does not exist or is fully paid.")
            context["back_url"] = reverse_lazy("invoice-detail", kwargs={"pk": invoice_application.invoice.pk})

        return context


class PaymentListView(PermissionRequiredMixin, ListView):
    model = Payment
    template_name = "payments/payment_list.html"
    permission_required = "payments.view_payment"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Payment List"
        return context

    def get_queryset(self):
        """
        Return only the payments created by the current user if the user is not a superuser or part of the group
        'Administration Office' or 'PowerUsers'
        """
        queryset = super().get_queryset()
        if (
            self.request.user.is_superuser
            or self.request.user.groups.filter(name__in=["Administration Office", "PowerUsers"]).exists()
        ):
            return queryset

        return queryset.filter(created_by=self.request.user)
