import os
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.core.files.storage import default_storage
from products.models import Product, Task
from customers.models import Customer
from products.models import Product
from core.utils.helpers import whitespaces_to_underscores

class DocApplicationManager(models.Manager):
    def search_doc_applications(self, query):
        return self.filter(
            models.Q(product__name__icontains=query) |
            models.Q(product__code__icontains=query) |
            models.Q(customer__full_name__icontains=query) |
            models.Q(doc_date__icontains=query)
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
    doc_date = models.DateField()
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_by_doc_application')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='updated_by_doc_application', blank=True, null=True)
    objects = DocApplicationManager()

    @property
    def current_step(self):
        """Returns the current step of the application, which is the first non Completed step of the workflow."""
        return self.workflows.exclude(status='completed').first().step

    @property
    def current_task(self):
        """Returns the current task of the application, which is the first non Completed task of the workflow."""
        return self.workflows.exclude(status='completed').first().task

    @property
    def current_status(self):
        """Returns the current status of the application, which is the status of the first non Completed step of the workflow."""
        return self.workflows.exclude(status='completed').first().status

    class Meta:
        ordering = ['application_type']

    def __str__(self):
        return self.product.name + ' - ' + self.customer.full_name + ' - ' + self.doc_date.strftime('%d/%m/%Y')

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        return super(DocApplication, self).save(*args, **kwargs)



class RequiredDocument(models.Model):
    # helper function to construct the upload_to path
    def get_upload_to(instance, filename):
        base_doc_path = 'documents'
        # Get the extension of the original file
        _, extension = os.path.splitext(filename)
        # construct the filename preserving the extension
        doc_application = instance.doc_application
        filename = f"{whitespaces_to_underscores(instance.doc_type)}{extension}"
        # return the complete upload to path, which is:
        # documents/<customer_name>_<customer_id>/<doc_application_id>/<doc_type>.<extension>
        return f"{base_doc_path}/{whitespaces_to_underscores(doc_application.customer.full_name)}_{doc_application.customer.pk}/{doc_application.pk}/{filename}"

    doc_application = models.ForeignKey(DocApplication, related_name='required_documents', on_delete=models.CASCADE)
    doc_type = models.CharField(max_length=100)
    doc_number = models.CharField(max_length=50, blank=True)
    expiration_date = models.DateField(blank=True, null=True)
    file = models.FileField(upload_to=get_upload_to, blank=True)
    file_link = models.CharField(max_length=1024, blank=True)
    # metadata field to store the extracted metadata from the document
    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_by_required_document')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='updated_by_required_document', blank=True, null=True)

    @property
    def completed(self):
        return bool(self.file_link)

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_by_doc_workflow')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='updated_by_doc_workflow', blank=True, null=True)

    class Meta:
        ordering = ['application_date']

    def __str__(self):
        return self.task.name

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        return super(DocWorkflow, self).save(*args, **kwargs)
