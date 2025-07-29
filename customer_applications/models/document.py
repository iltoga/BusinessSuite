import os

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone

from core.utils.helpers import whitespaces_to_underscores
from products.models.document_type import DocumentType

from .doc_application import DocApplication


class DocumentManager(models.Manager):
    def search_documents(self, query):
        return self.filter(
            models.Q(doc_type__name__icontains=query)
            | models.Q(doc_number__icontains=query)
            | models.Q(details__icontains=query)
        )


class Document(models.Model):
    @staticmethod
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

    doc_application = models.ForeignKey(DocApplication, related_name="documents", on_delete=models.CASCADE)
    doc_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)
    doc_number = models.CharField(max_length=50, blank=True)
    expiration_date = models.DateField(blank=True, null=True, db_index=True)
    file = models.FileField(upload_to=get_upload_to, blank=True)
    file_link = models.CharField(max_length=1024, blank=True)
    # metadata field to store the extracted metadata from the document
    ocr_check = models.BooleanField(default=False)
    details = models.TextField(blank=True)
    completed = models.BooleanField(default=False)
    metadata = models.JSONField(blank=True, null=True)
    required = models.BooleanField(default=True)
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
        """Returns True if the document is expiring within its minimum validity period."""
        if self.expiration_date:
            min_validity = self.doc_application.product.documents_min_validity
            return bool(self.expiration_date < timezone.now().date() + timezone.timedelta(days=min_validity))
        return False

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

        # In case of an update operation, if a new file is being uploaded
        if self.pk is not None and self.file and self.file.name:
            orig = Document.objects.get(pk=self.pk)
            # If a different file is being uploaded
            if orig.file and orig.file.name != self.file.name:
                # Get the upload_to path
                file_path = Document.get_upload_to(self, self.file.name)
                # Check if the file with same path exists and delete it
                if default_storage.exists(file_path):
                    default_storage.delete(file_path)
            self.file_link = self.file.url
        else:
            self.file_link = ""

        if self.metadata is not None and self.metadata != {}:
            self.ocr_check = True
        else:
            self.ocr_check = False

        super().save(*args, **kwargs)
