import os
from logging import getLogger

from core.utils.helpers import whitespaces_to_underscores
from customer_applications.services.document_expiration_state_service import DocumentExpirationStateService
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models, transaction
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from products.models.document_type import DocumentType

from .doc_application import DocApplication

logger = getLogger(__name__)


class DocumentManager(models.Manager):
    def search_documents(self, query):
        return self.filter(
            models.Q(doc_type__name__icontains=query)
            | models.Q(doc_number__icontains=query)
            | models.Q(details__icontains=query)
        )


# Moved out of Document class to allow Django to serialize it for migrations
def get_upload_to(instance, filename):
    """
    Returns the upload_to path for the file field.
    """
    _, extension = os.path.splitext(filename)
    filename = f"{whitespaces_to_underscores(instance.doc_type.name)}{extension}"
    # return the complete upload to path, which is:
    # documents/<customer_name>_<customer_id>/<doc_application_id>/<doc_type>.<extension>
    doc_application_folder = instance.doc_application.upload_folder
    return f"{doc_application_folder}/{filename}"


class Document(models.Model):

    doc_application = models.ForeignKey(DocApplication, related_name="documents", on_delete=models.CASCADE)
    doc_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)
    doc_number = models.CharField(max_length=50, blank=True)
    expiration_date = models.DateField(blank=True, null=True, db_index=True)
    file = models.FileField(upload_to=get_upload_to, blank=True)
    file_link = models.CharField(max_length=1024, blank=True)
    # True when AI validation has been requested/performed for this document
    ai_validation = models.BooleanField(default=False)
    details = models.TextField(blank=True)
    completed = models.BooleanField(default=False)
    metadata = models.JSONField(blank=True, null=True)
    required = models.BooleanField(default=True)

    # AI validation fields
    AI_VALIDATION_NONE = ""
    AI_VALIDATION_PENDING = "pending"
    AI_VALIDATION_VALIDATING = "validating"
    AI_VALIDATION_VALID = "valid"
    AI_VALIDATION_INVALID = "invalid"
    AI_VALIDATION_ERROR = "error"
    AI_VALIDATION_CHOICES = [
        (AI_VALIDATION_NONE, "Not requested"),
        (AI_VALIDATION_PENDING, "Pending"),
        (AI_VALIDATION_VALIDATING, "Validating"),
        (AI_VALIDATION_VALID, "Valid"),
        (AI_VALIDATION_INVALID, "Invalid"),
        (AI_VALIDATION_ERROR, "Error"),
    ]
    ai_validation_status = models.CharField(max_length=20, blank=True, default="", choices=AI_VALIDATION_CHOICES)
    ai_validation_result = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_by_document"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_by_document",
        blank=True,
        null=True,
    )
    objects = DocumentManager()

    class Meta:
        ordering = ["-updated_at"]

    @property
    def is_expired(self):
        if self.expiration_date:
            return self.expiration_date < timezone.now().date()
        return False

    @property
    def is_expiring(self):
        """Returns True if the document expiration is within the configured threshold window."""
        return DocumentExpirationStateService().evaluate(self).state == DocumentExpirationStateService.STATE_EXPIRING

    @property
    def updated_or_created_at(self):
        return self.updated_at or self.created_at

    @property
    def updated_or_created_by(self):
        return self.updated_by or self.created_by

    def __str__(self):
        return (
            self.doc_type.name
            + " - "
            + self.doc_application.product.name
            + " - "
            + self.doc_application.customer.full_name
            + " - "
            + self.doc_application.doc_date.strftime("%d/%m/%Y")
        )

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        if self.pk is None:
            self.created_at = timezone.now()

        # Check each field separately
        is_file_filled = self.doc_type.has_file and self.file and self.file.name != ""
        is_details_filled = self.details != ""
        is_doc_number_filled = self.doc_type.has_doc_number and self.doc_number != ""
        is_expiration_date_filled = self.doc_type.has_expiration_date and self.expiration_date is not None
        # if file and details are required and one of them is filled
        is_file_or_details_filled = (
            self.doc_type.has_file and self.doc_type.has_details and (is_file_filled or is_details_filled)
        )
        # Check the overall condition for completed
        self.completed = any(
            [
                is_file_filled,  # if file is required and filled
                not self.doc_type.has_file
                and not self.doc_type.has_doc_number
                and not self.doc_type.has_expiration_date
                and is_details_filled,  # if only details are required and filled
                is_doc_number_filled,  # if document number is required and filled
                is_expiration_date_filled,  # if expiration date is required and filled
                is_file_or_details_filled,  # if file and details are required and one of them is filled
            ]
        )

        # In case of an update operation, handle file replacement or removal
        if self.pk is not None:
            orig = Document.objects.get(pk=self.pk)
            if orig.file and (not self.file or orig.file.name != self.file.name):
                if default_storage.exists(orig.file.name):
                    default_storage.delete(orig.file.name)

        if self.file:
            self.file_link = self.file.url
        else:
            self.file_link = ""

        self.ai_validation = self.ai_validation_status in {
            self.AI_VALIDATION_PENDING,
            self.AI_VALIDATION_VALIDATING,
            self.AI_VALIDATION_VALID,
            self.AI_VALIDATION_INVALID,
            self.AI_VALIDATION_ERROR,
        }

        super().save(*args, **kwargs)


@receiver(pre_delete, sender=Document)
def pre_delete_document_storage_signal(sender, instance, **kwargs):
    # Keep storage paths before deleting DB row.
    file_path = getattr(instance.file, "name", "") or ""
    instance._storage_file_path = file_path
    instance._storage_folder_path = os.path.dirname(file_path).strip("/") if file_path else ""


@receiver(post_delete, sender=Document)
def post_delete_document_storage_signal(sender, instance, **kwargs):
    file_path = getattr(instance, "_storage_file_path", "") or ""
    if not file_path:
        return

    folder_path = getattr(instance, "_storage_folder_path", "") or ""
    document_id = instance.id

    def _queue_storage_cleanup():
        try:
            from customer_applications.tasks import cleanup_document_storage_task

            cleanup_document_storage_task(file_path=file_path, folder_path=folder_path or None)
        except Exception as exc:
            # Do not block document deletion when queueing storage cleanup fails.
            logger.warning("Failed to queue storage cleanup for document #%s: %s", document_id, exc)

    try:
        transaction.on_commit(_queue_storage_cleanup)
    except Exception as exc:
        logger.warning("Failed registering storage cleanup on_commit for document #%s: %s", document_id, exc)


@receiver(post_save, sender=Document)
def update_doc_application_status_on_document_save(sender, instance, **kwargs):
    doc_application = instance.doc_application
    if doc_application and doc_application.status != DocApplication.STATUS_COMPLETED:
        # Recalculate status when documents change so the application leaves pending once requirements are met.
        doc_application.save()
