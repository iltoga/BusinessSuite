from django.core.exceptions import ValidationError
import datetime
import re

def validate_phone_number(value):
    if not re.match(r"^\+?1?\d{9,15}$", value):
        raise ValidationError('Invalid phone number.')

def validate_birthdate(value):
    if value > datetime.date.today():
        raise ValidationError('Birthdate cannot be in the future.')

def validate_document_id(value):
    if len(value) < 5:
        raise ValidationError('Document ID is too short.')

def validateEmail( email ):
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    try:
        validate_email( email )
        return True
    except ValidationError:
        return False

def validateDocumentType( document_type ):
    if document_type not in ['Passport', 'KTP', 'SIM']:
        raise ValidationError('Invalid document type.')

def validateExpirationDate( expiration_date ):
    if expiration_date < datetime.date.today():
        raise ValidationError('Expiration date cannot be in the past.')