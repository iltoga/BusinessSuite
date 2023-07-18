# forms.py
import re
from typing import Any

from django import forms
from django.core import serializers
from django.forms.fields import Field
from django.utils import timezone
from matplotlib import widgets

import customer_applications
from customer_applications.models import DocApplication
from customers.models import Customer
from invoices.models import Invoice, InvoiceApplication


class InvoiceCreateForm(forms.ModelForm):
    invoice_no = forms.CharField(required=False)

    class Meta:
        model = Invoice
        fields = ["customer", "invoice_no", "invoice_date", "due_date", "total_amount", "status", "notes", "sent"]
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date", "value": timezone.now().strftime("%Y-%m-%d")}),
            "due_date": forms.DateInput(attrs={"type": "date", "value": timezone.now().strftime("%Y-%m-%d")}),
            "total_amount": forms.NumberInput(attrs={"readonly": True}),
            "notes": forms.Textarea(),
            "sent": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["customer"].disabled = True
        else:
            # invoice_no is automatically generated when saving the invoice
            self.fields["invoice_no"].widget = forms.HiddenInput()
            self.fields["status"].widget = forms.HiddenInput()
            self.fields["sent"].widget = forms.HiddenInput()
            self.fields["customer"].widget = forms.Select(attrs={"class": "select2"})
            self.fields["customer"].queryset = Customer.objects.all().active()

        if self.initial:
            customer = self.initial.get("customer", None)
            if customer:
                self.fields["customer"].queryset = Customer.objects.filter(pk=customer.pk)

    def clean(self):
        cleaned_data = super().clean()
        invoice_no = cleaned_data.get("invoice_no")

        # invoice_no is the unique field we're using for duplicate checks
        if invoice_no and self.instance.pk is None:
            invoice_applications = self.cleaned_data.get("invoice_applications")

            for application_form in invoice_applications:
                # clean() method is called on each form automatically
                customer_application = application_form.cleaned_data.get("customer_application")

                if InvoiceApplication.objects.filter(
                    invoice__invoice_no=invoice_no, customer_application=customer_application
                ).exists():
                    raise forms.ValidationError(
                        "This customer application has already been added.", code="invalid_customer_application"
                    )
        return cleaned_data


class InvoiceUpdateForm(forms.ModelForm):
    invoice_no = forms.CharField(required=False)

    class Meta:
        model = Invoice
        fields = ["customer", "invoice_no", "invoice_date", "due_date", "total_amount", "status", "notes", "sent"]
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date", "value": timezone.now().strftime("%Y-%m-%d")}),
            "due_date": forms.DateInput(attrs={"type": "date", "value": timezone.now().strftime("%Y-%m-%d")}),
            "total_amount": forms.NumberInput(attrs={"readonly": True}),
            "notes": forms.Textarea(),
            "sent": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["customer"].disabled = True
        self.fields["invoice_no"].disabled = True
        self.fields["invoice_date"].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        invoice_no = cleaned_data.get("invoice_no")

        # invoice_no is the unique field we're using for duplicate checks
        if invoice_no and self.instance.pk is None:
            invoice_applications = self.cleaned_data.get("invoice_applications")

            for application_form in invoice_applications:
                # clean() method is called on each form automatically
                customer_application = application_form.cleaned_data.get("customer_application")

                if InvoiceApplication.objects.filter(
                    invoice__invoice_no=invoice_no, customer_application=customer_application
                ).exists():
                    raise forms.ValidationError(
                        "This customer application has already been added.", code="invalid_customer_application"
                    )
        return cleaned_data


class InvoiceApplicationCreateForm(forms.ModelForm):
    class Meta:
        model = InvoiceApplication
        fields = ["customer_application", "amount"]
        widgets = {
            "amount": forms.NumberInput(),
        }

    def __init__(self, *args, customer_applications=None, selected_customer_application=None, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields["customer_application"].queryset = DocApplication.objects.filter(
                pk=self.instance.customer_application.pk
            )
        elif selected_customer_application:
            self.fields["customer_application"].queryset = DocApplication.objects.filter(
                pk=selected_customer_application.pk
            )
        else:
            self.fields["customer_application"].queryset = customer_applications

    def clean(self):
        """Checks that the paid amount is not greater than the due amount."""
        cleaned_data = super().clean()
        amount = cleaned_data.get("amount", 0)
        paid_amount = cleaned_data.get("paid_amount", 0)

        if paid_amount > amount:
            raise forms.ValidationError("Paid amount cannot be greater than due amount.", code="invalid_amount")


class InvoiceApplicationUpdateForm(forms.ModelForm):
    # add extra (calculated) field paid_amount and payment_status (read-only)
    paid_amount = forms.DecimalField(max_digits=12, decimal_places=2, required=False)
    payment_status = forms.CharField(max_length=20, required=False)

    class Meta:
        model = InvoiceApplication
        fields = ["customer_application", "amount"]
        widgets = {
            "amount": forms.NumberInput(),
        }

    def __init__(self, *args, customer_applications=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["customer_application"].queryset = customer_applications
        self.fields["paid_amount"].disabled = True
        self.fields["payment_status"].disabled = True

        # Set initial values for paid_amount and payment_status
        if self.instance and self.instance.pk:
            self.initial["paid_amount"] = self.instance.paid_amount
            self.initial["payment_status"] = self.instance.get_status_display()

    def clean(self):
        """Checks that the paid amount is not greater than the due amount."""
        cleaned_data = super().clean()
        amount = cleaned_data.get("amount", 0)
        paid_amount = cleaned_data.get("paid_amount", 0)

        if paid_amount > amount:
            raise forms.ValidationError("Paid amount cannot be greater than due amount.", code="invalid_amount")


class BaseInvoiceApplicationFormSet(forms.BaseInlineFormSet):
    def clean(self):
        """Checks that at least one application has been entered."""
        super().clean()

        if any(self.errors):
            return

        if not any(form.cleaned_data and not form.cleaned_data.get("DELETE", False) for form in self.forms):
            raise forms.ValidationError("At least one application is required.", code="missing_application")
