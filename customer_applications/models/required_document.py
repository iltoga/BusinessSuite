import os
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.files.storage import default_storage
from core.utils.helpers import whitespaces_to_underscores
from .doc_application import DocApplication

class RequiredDocument(models.Model):
    def get_upload_to(instance, filename):
        """
        Returns the upload_to path for the file field.
        """
        base_doc_path = 'documents'
        _, extension = os.path.splitext(filename)
        doc_application = instance.doc_application
        filename = f"{whitespaces_to_underscores(instance.doc_type)}{extension}"
        # return the complete upload to path, which is:
        # documents/<customer_name>_<customer_id>/<doc_application_id>/<doc_type>.<extension>
        return f"{base_doc_path}/{whitespaces_to_underscores(doc_application.customer.full_name)}_{doc_application.customer.pk}/application_{doc_application.pk}/{filename}"

    doc_application = models.ForeignKey(DocApplication, related_name='required_documents', on_delete=models.CASCADE)
    doc_type = models.CharField(max_length=100)
    doc_number = models.CharField(max_length=50, blank=True)
    expiration_date = models.DateField(blank=True, null=True)
    file = models.FileField(upload_to=get_upload_to, blank=True)
    file_link = models.CharField(max_length=1024, blank=True)
    # metadata field to store the extracted metadata from the document
    ocr_check = models.BooleanField(default=False)
    completed = models.BooleanField(default=False)
    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_by_required_document')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='updated_by_required_document', blank=True, null=True)

    class Meta:
        ordering = ['doc_type']

    def __str__(self):
        return self.doc_type + ' - ' + self.doc_application.product.name + ' - ' + self.doc_application.customer.full_name + ' - ' + self.doc_application.doc_date.strftime('%d/%m/%Y')

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        # In case of an update operation, if a new file is being uploaded
        if self.pk is not None and self.file:
            orig = RequiredDocument.objects.get(pk=self.pk)
            # If a different file is being uploaded
            if orig.file and orig.file.name != self.file.name:
                # Get the upload_to path
                file_path = self.get_upload_to(self.file.name)
                # Check if the file with same path exists and delete it
                if default_storage.exists(file_path):
                    default_storage.delete(file_path)
        super().save(*args, **kwargs)

        if self.file:
            self.file_link = self.file.url
            self.completed = True
        else:
            self.file_link = ''
            self.completed = False

        super(RequiredDocument, self).save(*args, **kwargs)
