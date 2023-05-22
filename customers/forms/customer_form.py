from django import forms
from core.utils.form_validators import validate_phone_number, validate_birthdate, validate_document_id, validateEmail, validateDocumentType, validateExpirationDate

from customers.models import Customer

DOCUMENT_TYPE_CHOICES = [
    ('', '---------'),
    ('Passport', 'Passport'),
    ('KTP', 'KTP'),
    ('SIM', 'SIM'),
]

TITLES_CHOICES = [
    ('', '---------'),
    ('Mr', 'Mr'),
    ('Mrs', 'Mrs'),
    ('Ms', 'Ms'),
    ('Miss', 'Miss'),
    ('Dr', 'Dr'),
    ('Prof', 'Prof'),
]

NOTIFY_BY_CHOICES = [
    ('', '---------'),
    ('Email', 'Email'),
    ('SMS', 'SMS'),
    ('WhatsApp', 'WhatsApp'),
    ('Telegram', 'Telegram'),
    ('Telephone', 'Telephone'),
]

class CustomerForm(forms.ModelForm):
    telephone = forms.CharField(validators=[validate_phone_number])
    birthdate = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), validators=[validate_birthdate])
    document_type = forms.CharField(validators=[validateDocumentType])
    document_id = forms.CharField(validators=[validate_document_id])
    email = forms.CharField(validators=[validateEmail])
    expiration_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), validators=[validateExpirationDate])
    document_type = forms.ChoiceField(choices=DOCUMENT_TYPE_CHOICES, widget=forms.Select, required=True)
    title = forms.ChoiceField(choices=TITLES_CHOICES, widget=forms.Select, required=True)
    notify_by = forms.ChoiceField(choices=NOTIFY_BY_CHOICES, widget=forms.Select, required=True)

    class Meta:
        model = Customer
        fields = ['full_name', 'email', 'telephone', 'title', 'citizenship', 'birthdate',
                  'address_bali', 'address_abroad', 'document_type', 'document_id', 'expiration_date',
                  'notify_expiration', 'notify_by']
