from django import forms
from django.core.exceptions import ValidationError
from common.utils.form_validators import validate_phone_number, validate_birthdate, validate_document_id, validateEmail, validateDocumentType, validateExpirationDate

from customers.models import Customer

class CustomerForm(forms.ModelForm):
    telephone = forms.CharField(validators=[validate_phone_number])
    birthdate = forms.DateField(validators=[validate_birthdate])
    document_type = forms.CharField(validators=[validateDocumentType])
    document_id = forms.CharField(validators=[validate_document_id])
    email = forms.CharField(validators=[validateEmail])
    expiration_date = forms.DateField(validators=[validateExpirationDate])

    class Meta:
        model = Customer
        fields = ['full_name', 'email', 'telephone', 'title', 'citizenship', 'birthdate',
                  'address_bali', 'address_abroad', 'document_type', 'document_id', 'expiration_date',
                  'notify_expiration', 'notify_by', 'notification_sent']
