# forms.py
from django import forms

from invoices.models import Invoice, InvoiceApplication, Payment


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["customer", "due_date", "notes"]


class InvoiceApplicationForm(forms.ModelForm):
    class Meta:
        model = InvoiceApplication
        fields = ["customer_application", "due_amount"]


class BaseInvoiceApplicationFormSet(forms.BaseInlineFormSet):
    def clean(self):
        """Checks that at least one application has been entered."""
        super().clean()

        if any(self.errors):
            return

        if not any(form.cleaned_data and not form.cleaned_data.get("DELETE", False) for form in self.forms):
            raise forms.ValidationError("At least one application is required.", code="missing_application")


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["invoice_application", "amount", "from_customer", "notes"]
