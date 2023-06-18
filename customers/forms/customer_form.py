from django import forms

from customers.models import NOTIFY_BY_CHOICES, Customer


class CustomerForm(forms.ModelForm):
    birthdate = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    address_bali = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), required=False)
    address_abroad = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), required=False)
    notify_documents_expiration = forms.BooleanField(widget=forms.CheckboxInput, required=False)
    notify_by = forms.ChoiceField(choices=NOTIFY_BY_CHOICES, required=False)

    class Meta:
        model = Customer
        fields = [
            "full_name",
            "email",
            "telephone",
            "whatsapp",
            "telegram",
            "title",
            "citizenship",
            "birthdate",
            "address_bali",
            "address_abroad",
            "notify_documents_expiration",
            "notify_by",
        ]
