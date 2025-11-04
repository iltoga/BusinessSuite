from collections import OrderedDict
from xml.dom import ValidationErr

from django import forms
from django.shortcuts import get_object_or_404
from matplotlib import widgets

from core.models import CountryCode
from customers.models import GENDERS, NOTIFY_BY_CHOICES, Customer


class CustomerForm(forms.ModelForm):
    # add first_name with validation: first letter must be uppercase
    first_name = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={"pattern": "[A-Z][a-z]*"}),
    )
    gender = forms.ChoiceField(choices=GENDERS, required=False)
    notify_documents_expiration = forms.BooleanField(widget=forms.CheckboxInput, required=False)
    notify_by = forms.ChoiceField(choices=NOTIFY_BY_CHOICES, required=False)
    passport_file = forms.FileField(
        required=False,
        label="Import data from Passport",
    )
    birthdate = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), required=False)
    telephone = forms.CharField(required=True)

    class Meta:
        model = Customer
        fields = [
            "first_name",
            "last_name",
            "title",
            "gender",
            "nationality",
            "birthdate",
            "email",
            "telephone",
            "whatsapp",
            "telegram",
            "facebook",
            "instagram",
            "twitter",
            "address_bali",
            "address_abroad",
            "notify_documents_expiration",
            "notify_by",
        ]

        widgets = {
            "address_bali": forms.Textarea(attrs={"rows": 5}),
            "address_abroad": forms.Textarea(attrs={"rows": 5}),
            "nationality": forms.Select(attrs={"class": "select2"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        # Move 'passport_file' to the beginning of the form fields
        self.fields = OrderedDict([("passport_file", self.fields["passport_file"])] + list(self.fields.items()))

    # def save(self, commit=True):
    #     instance = super().save(commit=False)

    #     # check if instance.nationality is a string, which means it might be the alpha3_code of a CountryCode
    #     if isinstance(instance.nationality, str):
    #         cc = CountryCode.objects.filter(alpha3_code=instance.nationality).first()
    #         if not cc:
    #             raise forms.ValidationError(f"Country code {instance.nationality} not found.")
    #         else:
    #             instance.nationality = cc

    #     if commit:
    #         instance.save()
    #     return instance
