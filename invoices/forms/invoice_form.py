# forms.py
from django import forms
from django.core import serializers
from django.utils import timezone

from customer_applications.models import DocApplication
from customers.models import Customer
from invoices.models import Invoice, InvoiceApplication, Payment


class InvoiceForm(forms.ModelForm):
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

    def __init__(self, *args, customer=None, **kwargs):
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

        # populate customer field if customer is provided
        if customer:
            self.fields["customer"].initial = customer
            self.fields["customer"].queryset = Customer.objects.get(pk=customer.pk)


class InvoiceApplicationForm(forms.ModelForm):
    class Meta:
        model = InvoiceApplication
        fields = ["customer_application", "due_amount", "paid_amount", "payment_status"]
        widgets = {
            "due_amount": forms.NumberInput(),
            "paid_amount": forms.NumberInput(),
        }

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields["customer_application"].widget = forms.TextInput(attrs={"readonly": True})
        else:
            queryset = DocApplication.objects.filter(customer=customer).filter_by_document_collection_completed()
            self.fields["customer_application"].queryset = queryset

            # Serializing queryset into JSON
            self.customer_applications_json = serializers.serialize("json", queryset)

            self.fields["paid_amount"].widget = forms.HiddenInput()
            self.fields["payment_status"].widget = forms.HiddenInput()

    def clean_customer_application(self):
        """Checks that the customer application has not already been added."""
        customer_application = self.cleaned_data["customer_application"]
        invoice = self.instance.invoice
        if invoice.invoiceapplication_set.filter(customer_application=customer_application).exists():
            raise forms.ValidationError(
                "This customer application has already been added.", code="invalid_customer_application"
            )
        return customer_application

    def clean(self):
        """Checks that the paid amount is not greater than the due amount."""
        cleaned_data = super().clean()
        due_amount = cleaned_data.get("due_amount", 0)
        paid_amount = cleaned_data.get("paid_amount", 0)

        if paid_amount > due_amount:
            raise forms.ValidationError("Paid amount cannot be greater than due amount.", code="invalid_amount")


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
