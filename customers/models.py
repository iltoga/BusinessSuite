import logging
import os
import shutil

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from core.utils.form_validators import validate_birthdate, validate_email, validate_phone_number
from core.utils.helpers import whitespaces_to_underscores

logger = logging.getLogger(__name__)

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
    # Fields are ordered: default fields, custom fields, and finally relationships
    id = models.AutoField(primary_key=True)
    first_name = models.CharField(max_length=50, db_index=True)
    last_name = models.CharField(max_length=50, db_index=True)
    email = models.EmailField(
        max_length=50, unique=True, blank=True, null=True, validators=[validate_email], db_index=True
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
    facebook = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    instagram = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    twitter = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    title = models.CharField(choices=TITLES_CHOICES, max_length=50)
    nationality = models.CharField(max_length=100, db_index=True)
    birthdate = models.DateField(validators=[validate_birthdate])
    gender = models.CharField(choices=GENDERS, max_length=5, blank=True, null=True)
    address_bali = models.TextField(blank=True, null=True)
    address_abroad = models.TextField(blank=True, null=True)
    notify_documents_expiration = models.BooleanField(default=True)
    notify_by = models.CharField(choices=NOTIFY_BY_CHOICES, max_length=50, blank=True, null=True)
    notification_sent = models.BooleanField(default=False)

    objects = CustomerManager()

    class Meta:
        ordering = ["first_name", "last_name"]
        unique_together = (("first_name", "last_name", "birthdate"),)

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def clean(self):
        if self.notify_documents_expiration and not self.notify_by:
            raise ValidationError("If notify expiration is true, notify by is mandatory.")

    @property
    def upload_folder(self):
        base_doc_path = settings.DOCUMENTS_FOLDER
        return f"{base_doc_path}/{whitespaces_to_underscores(self.full_name)}_{self.pk}"

    def delete_customer_files(self):
        # get media root path from settings
        media_root = settings.MEDIA_ROOT
        # delete the folder containing the customer's files
        try:
            shutil.rmtree(os.path.join(media_root, self.upload_folder))
        except FileNotFoundError:
            logger.info("Folder not found: %s", self.upload_folder)


@receiver(pre_delete, sender=Customer)
def pre_delete_customer_signal(sender, instance, **kwargs):
    # retain the folder path before deleting the customer
    instance.folder_path = instance.upload_folder


@receiver(post_delete, sender=Customer)
def post_delete_customer_signal(sender, instance, **kwargs):
    logger.info("Deleted: %s", instance)
    # delete the customer's files
    instance.delete_customer_files()
