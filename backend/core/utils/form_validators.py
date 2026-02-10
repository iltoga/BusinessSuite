import datetime
import re

from django.core.exceptions import ValidationError


def validate_phone_number(value):
    if not re.match(r"^\+?1?\d{9,15}$", value):
        raise ValidationError("Invalid phone number.")


def normalize_phone_number(value):
    """Normalize phone numbers by trimming spaces and removing separators."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return ""

    has_plus = value.startswith("+")
    digits_only = re.sub(r"\D", "", value)
    if has_plus:
        return f"+{digits_only}"
    return digits_only


def validate_birthdate(value):
    if value > datetime.date.today():
        raise ValidationError("Birthdate cannot be in the future.")


def validate_document_id(value):
    if len(value) < 5:
        raise ValidationError("Document ID is too short.")


def validate_email(email):
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    try:
        validate_email(email)
        return True
    except ValidationError:
        return False


def validateDocumentType(document_type):
    if document_type not in ["Passport", "KTP", "SIM"]:
        raise ValidationError("Invalid document type.")


def validateExpirationDate(expiration_date):
    if expiration_date < datetime.date.today():
        raise ValidationError("Expiration date cannot be in the past.")
