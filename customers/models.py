from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.utils.form_validators import validate_birthdate, validate_phone_number, validateEmail

TITLES_CHOICES = [
    ("", "---------"),
    ("Mr", "Mr"),
    ("Mrs", "Mrs"),
    ("Ms", "Ms"),
    ("Miss", "Miss"),
    ("Dr", "Dr"),
    ("Prof", "Prof"),
]

NOTIFY_BY_CHOICES = [
    ("", "---------"),
    ("Email", "Email"),
    ("SMS", "SMS"),
    ("WhatsApp", "WhatsApp"),
    ("Telegram", "Telegram"),
    ("Telephone", "Telephone"),
]

GENDERS = [
    ("", "---------"),
    ("M", "Male"),
    (
        "F",
        "Female",
    ),
]


class CustomerManager(models.Manager):
    def search_customers(self, query):
        return self.filter(
            models.Q(first_name__icontains=query)
            | models.Q(last_name__icontains=query)
            | models.Q(email__icontains=query)
            | models.Q(telephone__icontains=query)
            | models.Q(telegram__icontains=query)
            | models.Q(whatsapp__icontains=query)
        )


class Customer(models.Model):
    id = models.AutoField(primary_key=True)
    first_name = models.CharField(max_length=50, db_index=True)
    last_name = models.CharField(max_length=50, db_index=True)
    email = models.EmailField(
        max_length=50, unique=True, blank=True, null=True, validators=[validateEmail], db_index=True
    )
    telephone = models.CharField(
        max_length=50, unique=True, blank=True, null=True, validators=[validate_phone_number], db_index=True
    )
    whatsapp = models.CharField(
        max_length=50, unique=True, blank=True, null=True, validators=[validate_phone_number], db_index=True
    )
    telegram = models.CharField(
        max_length=50, unique=True, blank=True, null=True, validators=[validate_phone_number], db_index=True
    )
    # social media accounts
    facebook = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    instagram = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    twitter = models.CharField(max_length=50, blank=True, null=True, db_index=True)

    title = models.CharField(choices=TITLES_CHOICES, max_length=50)
    nationality = models.CharField(max_length=100, db_index=True)
    birthdate = models.DateField(validators=[validate_birthdate])
    gender = models.CharField(max_length=1, blank=True, null=True)
    address_bali = models.TextField(blank=True, null=True)
    address_abroad = models.TextField(blank=True, null=True)
    notify_documents_expiration = models.BooleanField(default=True)
    notify_by = models.CharField(choices=NOTIFY_BY_CHOICES, max_length=50, blank=True, null=True)
    notification_sent = models.BooleanField(default=False)
    objects = CustomerManager()

    class Meta:
        ordering = ["last_name", "first_name"]
        unique_together = (("first_name", "last_name", "birthdate"),)

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    # clean method is where you can add custom validations for your model
    # note: it can be used here or in the form class
    def clean(self):
        if self.notify_documents_expiration and not self.notify_by:
            raise ValidationError("If notify expiration is true, notify by is mandatory.")
