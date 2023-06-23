from collections import OrderedDict

from django import forms

from customers.models import GENDERS, NOTIFY_BY_CHOICES, Customer


class CustomerForm(forms.ModelForm):
    birthdate = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    address_bali = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), required=False)
    address_abroad = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), required=False)
    gender = forms.ChoiceField(choices=GENDERS, required=False)
    notify_documents_expiration = forms.BooleanField(widget=forms.CheckboxInput, required=False)
    notify_by = forms.ChoiceField(choices=NOTIFY_BY_CHOICES, required=False)
    passport_file = forms.FileField(required=False, label="Import data from Passport")

    class Meta:
        model = Customer
        fields = [
            "first_name",
            "last_name",
            "email",
            "telephone",
            "whatsapp",
            "telegram",
            "facebook",
            "instagram",
            "twitter",
            "title",
            "gender",
            "nationality",
            "birthdate",
            "address_bali",
            "address_abroad",
            "notify_documents_expiration",
            "notify_by",
        ]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        # Move 'passport_file' to the beginning of the form fields
        self.fields = OrderedDict([("passport_file", self.fields["passport_file"])] + list(self.fields.items()))
