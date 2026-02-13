from core.models import CountryCode
from customers.models import Customer
from django import forms
from django.utils import timezone


class CountryIdnModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        # Prefer country_idn when available, fallback to country
        return getattr(obj, "country_idn", None) or getattr(obj, "country", "")


class SuratPermohonanForm(forms.Form):
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        widget=forms.Select(attrs={"class": "select2"}),
        required=True,
        label="Customer",
    )
    doc_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=timezone.now,
        required=True,
        label="Application Date",
    )
    name = forms.CharField(max_length=255, required=True, label="Customer Name")
    VISA_TYPE_CHOICES = [
        ("voa", "VOA"),
        ("C1", "C1"),
    ]
    visa_type = forms.ChoiceField(
        choices=VISA_TYPE_CHOICES,
        required=True,
        label="Visa Type",
        initial="voa",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    gender = forms.CharField(max_length=50, required=False, label="Gender")
    country = CountryIdnModelChoiceField(
        queryset=CountryCode.objects.all().order_by("country"),
        required=False,
        label="Nationality",
        widget=forms.Select(attrs={"class": "form-select select2"}),
    )
    birth_place = forms.CharField(max_length=100, required=False, label="Birth Place")
    birthdate = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
        label="Birth Date",
    )
    passport_no = forms.CharField(max_length=50, required=False, label="Passport Number")
    passport_exp_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
        label="Passport Expiration Date",
    )
    address_bali = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Address in Bali",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = (
            Customer.objects.filter(active=True)
            .only("id", "first_name", "last_name", "company_name", "customer_type")
            .order_by("first_name", "last_name")
        )
