import time

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from invoices.models.invoice import InvoiceApplication

from .models import Payment


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["from_customer", "invoice_application", "payment_date", "payment_type", "amount"]
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"step": "10000"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Set initial amount based on invoice application if not already set
        if not self.is_bound and self.initial.get("invoice_application"):
            invoice_app = self.initial.get("invoice_application")
            if not self.initial.get("amount"):
                self.initial["amount"] = invoice_app.due_amount

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get("amount")
        invoice_application = cleaned_data.get("invoice_application")

        if amount and invoice_application:
            total_due_amount = invoice_application.invoice.total_due_amount

            if amount > total_due_amount:
                raise ValidationError("The payment amount exceeds the due amount.")

        return cleaned_data
