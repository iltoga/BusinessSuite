import os
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.core.files.storage import default_storage
from products.models import Product, Task
from customers.models import Customer
from products.models import Product

class DocApplicationManager(models.Manager):
    def search_doc_applications(self, query):
        return self.filter(
            models.Q(product__name__icontains=query) |
            models.Q(product__code__icontains=query) |
            models.Q(customer__full_name__icontains=query)
        )

class DocApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected')
    ]

    application_type = models.CharField(max_length=50, choices=Product.PRODUCT_TYPE_CHOICES, default='other')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    objects = DocApplicationManager()
    doc_date = models.DateField()

    @property
    def current_step(self):
        """Returns the current step of the application, which is the first pending step of the workflow."""
        return self.workflows.filter(status='pending').first()

    class Meta:
        ordering = ['application_type']

    def __str__(self):
        return self.product.name + ' - ' + self.customer.full_name + ' - ' + self.doc_date.strftime('%d/%m/%Y')



class RequiredDocument(models.Model):
    # helper function to construct the upload_to path
    def get_upload_to(instance, filename):
        base_doc_path = 'documents'
        # get today's date in the required format
        date_today = timezone.now().strftime("%Y-%m-%d")
        # Get the extension of the original file
        _, extension = os.path.splitext(filename)
        # construct the filename preserving the extension
        filename = f"{instance.doc_type}_{date_today}{extension}"
        # return the complete upload to path
        return f"{base_doc_path}/{instance.doc_application.customer.full_name}_{instance.doc_application.customer.pk}/{filename}"

    doc_application = models.ForeignKey(DocApplication, related_name='required_documents', on_delete=models.CASCADE)
    doc_type = models.CharField(max_length=100)
    doc_number = models.CharField(max_length=50, blank=True)
    expiration_date = models.DateField(blank=True, null=True)
    file = models.FileField(upload_to=get_upload_to, blank=True)
    file_link = models.CharField(max_length=1024, blank=True)
    # metadata field to store the extracted metadata from the document
    metadata = models.JSONField(blank=True, null=True)

    @property
    def completed(self):
        return bool(self.file_link)

    class Meta:
        ordering = ['doc_type']

    def __str__(self):
        return self.doc_type + ' - ' + self.doc_application.product.name + ' - ' + self.doc_application.customer.full_name + ' - ' + self.doc_application.doc_date.strftime('%d/%m/%Y')

    def save(self, *args, **kwargs):
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
        else:
            self.file_link = ''

        super(RequiredDocument, self).save(*args, **kwargs)


class DocWorkflow(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected')
    ]

    doc_application = models.ForeignKey(DocApplication, related_name='workflows', on_delete=models.CASCADE)
    task = models.OneToOneField(Task, on_delete=models.CASCADE)
    application_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['application_date']

    def __str__(self):
        return self.task.name
