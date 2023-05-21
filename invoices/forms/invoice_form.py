from django import forms
from django.core.exceptions import ValidationError

from invoices.models.invoice import Invoice

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['invoice_no', 'date', 'customer']

    def clean_invoice_no(self):
        invoice_no = self.cleaned_data.get('invoice_no')
        if Invoice.objects.is_invoice_no_exist:
            raise ValidationError("This invoice number already exists.")
        return invoice_no
