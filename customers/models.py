import logging
import os
import shutil

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.serializers import serialize
from django.db import models
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from core.models import CountryCode
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

CUSTOMER_TYPE_CHOICES = [
    ("person", "Person"),
    ("company", "Company"),
]


class CustomerQuerySet(models.QuerySet):
    # Return a queryset of active customers
    def active(self):
        return self.filter(active=True)


class CustomerManager(models.Manager):
    def get_queryset(self):
        return CustomerQuerySet(self.model, using=self._db)

    # Shortcut for Customer.objects.active()
    def active(self):
        return self.get_queryset().active()

    def search_customers(self, query):
        return self.filter(
            models.Q(first_name__icontains=query)
            | models.Q(last_name__icontains=query)
            | models.Q(company_name__icontains=query)
            | models.Q(email__icontains=query)
            | models.Q(telephone__icontains=query)
            | models.Q(telegram__icontains=query)
            | models.Q(whatsapp__icontains=query)
        )


class Customer(models.Model):
    # Fields are ordered: default fields, custom fields, and finally relationships
    id = models.AutoField(primary_key=True)
    title = models.CharField(choices=TITLES_CHOICES, max_length=50, blank=True, null=True)
    customer_type = models.CharField(
        max_length=20,
        choices=CUSTOMER_TYPE_CHOICES,
        default="person",
        db_index=True,
    )
    first_name = models.CharField(max_length=50, db_index=True, blank=True, null=True)
    last_name = models.CharField(max_length=50, db_index=True, blank=True, null=True)
    company_name = models.CharField(max_length=100, blank=True, null=True, db_index=True)
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
    npwp = models.CharField(max_length=30, blank=True, null=True, db_index=True, verbose_name="NPWP (Indonesia)")
    nationality = models.ForeignKey(
        CountryCode,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="customers",
        to_field="alpha3_code",
    )
    birthdate = models.DateField(validators=[validate_birthdate], blank=True, null=True)
    gender = models.CharField(choices=GENDERS, max_length=5, blank=True, null=True)
    address_bali = models.TextField(blank=True, null=True)
    address_abroad = models.TextField(blank=True, null=True)
    notify_documents_expiration = models.BooleanField(default=True)
    notify_by = models.CharField(choices=NOTIFY_BY_CHOICES, max_length=50, blank=True, null=True)
    notification_sent = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    objects = CustomerManager()

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.full_name

    def natural_key(self):
        """
        Returns a natural key that can be used to serialize this object.
        """
        return {
            "full_name": self.full_name,
            "email": self.email,
            "birthdate": self.birthdate,
            "active": self.active,
        }

    @property
    def full_name(self):
        # For companies, return company name if person names are not populated
        if self.customer_type == "company" and not (self.first_name and self.last_name):
            return self.company_name or "Unknown Company"
        # For persons or companies with person names
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        # Fallback
        return self.company_name or "Unknown"

    @property
    def full_name_with_company(self):
        if self.company_name:
            return f"{self.full_name} ({self.company_name})"
        return self.full_name

    def clean(self):
        if self.notify_documents_expiration and not self.notify_by:
            raise ValidationError("If notify expiration is true, notify by is mandatory.")
        # Custom validation: either first+last name, or company name, or all three must be populated
        first_last_filled = bool(self.first_name and self.last_name)
        company_filled = bool(self.company_name)
        if not (
            (first_last_filled and not company_filled)
            or (company_filled and not first_last_filled)
            or (first_last_filled and company_filled)
        ):
            raise ValidationError("Either both first and last name, or company name, or all three must be populated.")

    def save(self, *args, **kwargs):
        """
        Override save to convert empty strings to None for unique fields.
        This prevents duplicate empty values in unique fields (email, telephone, etc.)
        """
        # Convert empty strings to None for unique fields to avoid duplicate constraint violations
        if self.email == "":
            self.email = None
        if self.telephone == "":
            self.telephone = None
        if self.whatsapp == "":
            self.whatsapp = None
        if self.telegram == "":
            self.telegram = None

        super().save(*args, **kwargs)

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

    def doc_applications_to_json(
        self, filter_by_doc_collection_completed=True, exclude_already_invoiced=True, current_invoice_to_include=None
    ):
        # Serialize the customer's applications to JSON
        doc_application_qs = self.get_doc_applications_for_invoice(
            filter_by_doc_collection_completed, exclude_already_invoiced, current_invoice_to_include
        )

        # Serialize the queryset to JSON including the natural keys (related objects)
        json_obj = serialize("json", doc_application_qs, use_natural_foreign_keys=True)
        return json_obj

    def get_doc_applications_for_invoice(
        self, filter_by_doc_collection_completed=True, exclude_already_invoiced=True, current_invoice_to_include=None
    ):
        """
        Return a queryset of DocApplications that have their document collection completed (default behavior).
        If exclude_already_invoiced is True, exclude DocApplications that have already been invoiced.
        Note: by providing current_invoice_to_include, we can include DocApplications that are part of the current invoice (for updating an invoice).
        """
        # Optimize with select_related to prevent N+1 queries
        doc_application_qs = self.doc_applications.select_related("customer", "product").prefetch_related(
            "invoice_applications", "documents", "documents__doc_type"
        )
        if exclude_already_invoiced:
            doc_application_qs = doc_application_qs.exclude_already_invoiced(current_invoice_to_include)
        if filter_by_doc_collection_completed:
            doc_application_qs = doc_application_qs.filter_by_document_collection_completed()

        return doc_application_qs

    def can_be_deleted(self):
        # Block deletion if related invoices exist
        if self.invoices.exists():
            return False, "Cannot delete customer: related invoices exist."
        # Alert if related applications/workflows exist
        if self.doc_applications.exists():
            return True, "Warning: related applications/workflows exist."
        return True, None

    def delete(self, *args, **kwargs):
        can_delete, msg = self.can_be_deleted()
        if not can_delete:
            from django.db.models import ProtectedError

            raise ProtectedError(msg, self)
        super().delete(*args, **kwargs)


@receiver(pre_delete, sender=Customer)
def pre_delete_customer_signal(sender, instance, **kwargs):
    # retain the folder path before deleting the customer
    instance.folder_path = instance.upload_folder


@receiver(post_delete, sender=Customer)
def post_delete_customer_signal(sender, instance, **kwargs):
    logger.info("Deleted: %s", instance)
    # delete the customer's files
    instance.delete_customer_files()
