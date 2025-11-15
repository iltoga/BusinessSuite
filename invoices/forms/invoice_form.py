# forms.py
import re
from datetime import datetime
from typing import Any

from django import forms
from django.core import serializers
from django.db.models import Max
from django.forms.fields import Field
from django.utils import timezone
from matplotlib import widgets

import customer_applications
from customer_applications.models import DocApplication
from customers.models import Customer
from invoices.models import Invoice, InvoiceApplication


class InvoiceCreateForm(forms.ModelForm):
    # invoice_no shown as integer so user can override; min value will be set in __init__
    invoice_no = forms.IntegerField(required=False)

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
            # Show invoice_no so user can override it. We'll compute a suggested minimum
            # based on the invoice_date year (max invoice_no for that year + 1).
            self.fields["status"].widget = forms.HiddenInput()
            self.fields["sent"].widget = forms.HiddenInput()
            # determine year from data/initial or default to now
            year = None
            # If bound form, try to read provided invoice_date from data
            if hasattr(self, "data") and self.data.get("invoice_date"):
                try:
                    year = datetime.strptime(self.data.get("invoice_date"), "%Y-%m-%d").year
                except Exception:
                    year = None
            # fallback to initial or instance
            if year is None:
                invoice_date = self.initial.get("invoice_date") if self.initial else None
                if not invoice_date and getattr(self.instance, "invoice_date", None):
                    invoice_date = getattr(self.instance, "invoice_date")
                if invoice_date:
                    try:
                        year = invoice_date.year
                    except Exception:
                        # invoice_date might be a string
                        try:
                            year = datetime.strptime(str(invoice_date), "%Y-%m-%d").year
                        except Exception:
                            year = None
            if year is None:
                year = timezone.now().year

            # Compute suggested invoice number for the year
            from invoices.models.invoice import Invoice

            max_obj = Invoice.objects.filter(invoice_date__year=year).aggregate(max_no=Max("invoice_no"))
            proposed = (max_obj.get("max_no") or 0) + 1

            # configure invoice_no field widget with min and initial value
            self.fields["invoice_no"].widget = forms.NumberInput(attrs={"min": proposed})
            self.fields["invoice_no"].initial = proposed
            self.fields["customer"].widget = forms.Select(attrs={"class": "select2"})
            # Only load minimal fields needed for display - prevents loading all related data
            # Using only() dramatically reduces query count and data transfer
            self.fields["customer"].queryset = (
                Customer.objects.filter(active=True)
                .only("id", "first_name", "last_name", "company_name", "customer_type")
                .order_by("first_name", "last_name")
            )

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

            if invoice_applications:
                if invoice_applications:
                    if invoice_applications:
                        for application_form in invoice_applications:
                            # clean() method is called on each form automatically
                            customer_application = application_form.cleaned_data.get("customer_application")

                            if InvoiceApplication.objects.filter(
                                invoice__invoice_no=invoice_no, customer_application=customer_application
                            ).exists():
                                raise forms.ValidationError(
                                    "This customer application has already been added.",
                                    code="invalid_customer_application",
                                )
        return cleaned_data

    def clean_invoice_no(self):
        """Ensure provided invoice_no is >= proposed first-available number for invoice year.

        If empty, it's allowed (auto-generate on save).
        """
        invoice_no = self.cleaned_data.get("invoice_no")
        # determine year similar to __init__ logic
        year = None
        if self.data.get("invoice_date"):
            try:
                year = datetime.strptime(self.data.get("invoice_date"), "%Y-%m-%d").year
            except Exception:
                year = None
        if year is None:
            invoice_date = self.initial.get("invoice_date") if self.initial else None
            if not invoice_date and getattr(self.instance, "invoice_date", None):
                invoice_date = getattr(self.instance, "invoice_date")
            if invoice_date:
                try:
                    year = invoice_date.year
                except Exception:
                    try:
                        year = datetime.strptime(str(invoice_date), "%Y-%m-%d").year
                    except Exception:
                        year = None
        if year is None:
            year = timezone.now().year

        from invoices.models.invoice import Invoice

        max_obj = Invoice.objects.filter(invoice_date__year=year).aggregate(max_no=Max("invoice_no"))
        proposed = (max_obj.get("max_no") or 0) + 1

        if invoice_no is None:
            return invoice_no

        if invoice_no < proposed:
            raise forms.ValidationError(
                f"Invoice number cannot be lower than the first available number for {year} ({proposed})."
            )

        # Also check uniqueness
        if Invoice.objects.filter(invoice_no=invoice_no).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise forms.ValidationError("This invoice number is already in use.")

        return invoice_no


class InvoiceUpdateForm(forms.ModelForm):
    invoice_no = forms.CharField(required=False)

    class Meta:
        model = Invoice
        fields = ["customer", "invoice_no", "invoice_date", "due_date", "total_amount", "status", "notes", "sent"]
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "total_amount": forms.NumberInput(attrs={"readonly": True}),
            "notes": forms.Textarea(),
            "sent": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["customer"].disabled = True
        # invoice_no is CharField (not disabled) so it can be edited
        # invoice_date is NOT disabled so it can be edited

    def clean_invoice_no(self):
        """Validate invoice number hasn't changed (read-only for updates)."""
        invoice_no = self.cleaned_data.get("invoice_no")
        # Keep the original invoice_no - don't allow changes
        if self.instance and self.instance.pk:
            return str(self.instance.invoice_no)
        return invoice_no

    def clean(self):
        cleaned_data = super().clean()
        invoice_no = cleaned_data.get("invoice_no")

        # invoice_no is the unique field we're using for duplicate checks
        if invoice_no and self.instance.pk is None:
            invoice_applications = self.cleaned_data.get("invoice_applications")

            if invoice_applications:
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
        elif customer_applications is not None:
            # Use the provided queryset (could be empty .none() queryset)
            self.fields["customer_application"].queryset = customer_applications
        else:
            # No customer selected - use empty queryset to avoid loading all applications
            self.fields["customer_application"].queryset = DocApplication.objects.none()

        # If data is provided (form submission), check if there's a selected customer_application
        # and expand the queryset to include it (for dynamically added applications)
        if self.data:
            app_id = self.data.get(self.add_prefix("customer_application"))
            if app_id:
                try:
                    # Add the submitted application to the queryset if it's not already there
                    self.fields["customer_application"].queryset = self.fields[
                        "customer_application"
                    ].queryset | DocApplication.objects.filter(pk=app_id)
                except (ValueError, TypeError):
                    pass  # Invalid ID, let normal validation handle it

    def clean_customer_application(self):
        """Validate that the customer application exists and hasn't been invoiced yet."""
        customer_application = self.cleaned_data.get("customer_application")

        if not customer_application:
            raise forms.ValidationError("Customer application is required.")

        # If the application is not in the initial queryset (e.g., dynamically added via JavaScript),
        # we need to fetch it from the database to validate it
        if (
            customer_application.pk
            and not self.fields["customer_application"].queryset.filter(pk=customer_application.pk).exists()
        ):
            try:
                customer_application = DocApplication.objects.get(pk=customer_application.pk)
            except DocApplication.DoesNotExist:
                raise forms.ValidationError("Customer application does not exist.")

        # Check if this application is already invoiced
        if customer_application.invoice_applications.exists():
            raise forms.ValidationError(f"Application {customer_application} has already been invoiced.")

        return customer_application

    def clean(self):
        """Checks that the paid amount is not greater than the due amount."""
        cleaned_data = super().clean()
        amount = cleaned_data.get("amount")
        paid_amount = cleaned_data.get("paid_amount")

        if amount and paid_amount and paid_amount > amount:
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

        # Use provided queryset or limit to instance only
        if self.instance and self.instance.pk:
            self.fields["customer_application"].queryset = DocApplication.objects.filter(
                pk=self.instance.customer_application.pk
            )
        elif customer_applications is not None:
            # Use the provided queryset (could be empty .none() queryset)
            self.fields["customer_application"].queryset = customer_applications
        else:
            # No customer - use empty queryset to avoid loading all applications
            self.fields["customer_application"].queryset = DocApplication.objects.none()

        # If data is provided (form submission), check if there's a selected customer_application
        # and expand the queryset to include it (for dynamically added applications)
        if self.data:
            app_id = self.data.get(self.add_prefix("customer_application"))
            if app_id:
                try:
                    # Add the submitted application to the queryset if it's not already there
                    self.fields["customer_application"].queryset = self.fields[
                        "customer_application"
                    ].queryset | DocApplication.objects.filter(pk=app_id)
                except (ValueError, TypeError):
                    pass  # Invalid ID, let normal validation handle it

        self.fields["paid_amount"].disabled = True
        self.fields["payment_status"].disabled = True

        # Set initial values for paid_amount and payment_status
        if self.instance and self.instance.pk:
            self.initial["paid_amount"] = self.instance.paid_amount
            self.initial["payment_status"] = self.instance.get_status_display()

    def clean_customer_application(self):
        """Validate that the customer application exists and hasn't been invoiced yet (unless updating existing)."""
        customer_application = self.cleaned_data.get("customer_application")

        if not customer_application:
            raise forms.ValidationError("Customer application is required.")

        # If the application is not in the initial queryset (e.g., dynamically added via JavaScript),
        # we need to fetch it from the database to validate it
        if (
            customer_application.pk
            and not self.fields["customer_application"].queryset.filter(pk=customer_application.pk).exists()
        ):
            try:
                customer_application = DocApplication.objects.get(pk=customer_application.pk)
            except DocApplication.DoesNotExist:
                raise forms.ValidationError("Customer application does not exist.")

        # For existing invoice applications being updated, skip the already-invoiced check
        if self.instance and self.instance.pk:
            return customer_application

        # For new invoice applications being added, check if already invoiced by OTHER invoices
        # Exclude the current invoice if it exists (self.instance.invoice_id)
        existing_invoice_apps = customer_application.invoice_applications.all()

        # If we're editing an invoice, exclude applications from this invoice
        if hasattr(self, "instance") and self.instance and hasattr(self.instance, "invoice") and self.instance.invoice:
            existing_invoice_apps = existing_invoice_apps.exclude(invoice=self.instance.invoice)

        if existing_invoice_apps.exists():
            raise forms.ValidationError(f"Application {customer_application} has already been invoiced.")

        return customer_application

    def clean(self):
        """Checks that the paid amount is not greater than the due amount."""
        cleaned_data = super().clean()
        amount = cleaned_data.get("amount")
        paid_amount = cleaned_data.get("paid_amount")

        if amount and paid_amount and paid_amount > amount:
            raise forms.ValidationError("Paid amount cannot be greater than due amount.", code="invalid_amount")


class BaseInvoiceApplicationFormSet(forms.BaseInlineFormSet):
    def clean(self):
        """Checks that at least one application has been entered."""
        super().clean()

        if any(self.errors):
            return

        if not any(form.cleaned_data and not form.cleaned_data.get("DELETE", False) for form in self.forms):
            raise forms.ValidationError("At least one application is required.", code="missing_application")
