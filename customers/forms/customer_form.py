from django import forms
from django.core.exceptions import ValidationError
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
    address_bali = forms.CharField(widget=forms.Textarea(attrs={'rows': 5}), required=False)
    address_abroad = forms.CharField(widget=forms.Textarea(attrs={'rows': 5}), required=False)
    document_type = forms.CharField(validators=[validateDocumentType])
    document_id = forms.CharField(validators=[validate_document_id])
    email = forms.CharField(validators=[validateEmail])
    expiration_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), validators=[validateExpirationDate])
    document_type = forms.ChoiceField(choices=DOCUMENT_TYPE_CHOICES, widget=forms.Select, required=True)
    title = forms.ChoiceField(choices=TITLES_CHOICES, widget=forms.Select, required=True)
    notify_expiration = forms.BooleanField(widget=forms.CheckboxInput, required=False)
    notify_by = forms.ChoiceField(choices=NOTIFY_BY_CHOICES, widget=forms.Select, required=False)

    class Meta:
        model = Customer
        fields = ['full_name', 'email', 'telephone', 'title', 'citizenship', 'birthdate',
                  'address_bali', 'address_abroad', 'document_type', 'document_id', 'expiration_date',
                  'notify_expiration', 'notify_by']

    def clean(self):
        cleaned_data = super().clean()
        if not self.is_valid():
            return cleaned_data
        notify_expiration = cleaned_data.get('notify_expiration')
        notify_by = cleaned_data.get('notify_by')

        if notify_expiration and not notify_by:
            self.add_error('notify_by', ValidationError('This field is required when "notify expiration" is checked'))

        return cleaned_data