from collections import OrderedDict
from xml.dom import ValidationErr

from django import forms
from django.shortcuts import get_object_or_404
from matplotlib import widgets

from core.models import CountryCode
from customers.models import CUSTOMER_TYPE_CHOICES, GENDERS, NOTIFY_BY_CHOICES, Customer


class CustomerForm(forms.ModelForm):
    customer_type = forms.ChoiceField(
        choices=CUSTOMER_TYPE_CHOICES,
        required=True,
        initial="person",
        widget=forms.RadioSelect,
        label="Customer Type",
    )
    company_name = forms.CharField(
        max_length=100,
        required=False,
        label="Company Name",
    )
    # add first_name with validation: first letter must be uppercase
    first_name = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={"pattern": "[A-Z][a-z]*"}),
    )
    last_name = forms.CharField(
        max_length=50,
        required=False,
    )
    npwp = forms.CharField(
        max_length=30,
        required=False,
        label="NPWP (Tax ID)",
    )
    gender = forms.ChoiceField(choices=GENDERS, required=False)
    notify_documents_expiration = forms.BooleanField(widget=forms.CheckboxInput, required=False)
    notify_by = forms.ChoiceField(choices=NOTIFY_BY_CHOICES, required=False)
    passport_file = forms.FileField(
        required=False,
        label="Import data from Passport",
    )
    passport_number = forms.CharField(
        max_length=50,
        required=False,
        label="Passport Number",
    )
    passport_issue_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), required=False)
    passport_expiration_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), required=False)
    birthdate = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), required=False)
    birth_place = forms.CharField(max_length=100, required=False)
    telephone = forms.CharField(required=False)

    class Meta:
        model = Customer
        fields = [
            "customer_type",
            "company_name",
            "first_name",
            "last_name",
            "passport_number",
            "passport_issue_date",
            "passport_expiration_date",
            "title",
            "gender",
            "nationality",
            "birth_place",
            "birthdate",
            "npwp",
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
        # Move 'passport_file' after customer_type and company_name
        fields_order = [
            "customer_type",
            "company_name",
            "passport_file",
            "passport_number",
            "passport_issue_date",
            "passport_expiration_date",
        ]
        remaining_fields = [(k, v) for k, v in self.fields.items() if k not in fields_order]
        self.fields = OrderedDict([(k, self.fields[k]) for k in fields_order if k in self.fields] + remaining_fields)

    def clean(self):
        cleaned_data = super().clean()
        customer_type = cleaned_data.get("customer_type")
        first_name = cleaned_data.get("first_name")
        last_name = cleaned_data.get("last_name")
        company_name = cleaned_data.get("company_name")

        # Validation: person must have first and last name, company must have company name
        if customer_type == "person":
            if not first_name or not last_name:
                raise forms.ValidationError("First name and last name are required for person customers.")
        elif customer_type == "company":
            if not company_name:
                raise forms.ValidationError("Company name is required for company customers.")

        return cleaned_data

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
