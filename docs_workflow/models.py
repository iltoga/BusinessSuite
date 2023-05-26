from django.db import models
from products.models import Product, Task
from customers.models import Customer
from products.models import Product

class DocApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected')
    ]

    doc_type = models.CharField(max_length=50, choices=Product.PRODUCT_TYPE_CHOICES, default='other')
    product = models.OneToOneField(Product, on_delete=models.CASCADE)
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE)

    @property
    def current_step(self):
        """Returns the current step of the application, which is the first pending step of the workflow."""
        return self.workflows.filter(status='pending').first()

    class Meta:
        ordering = ['doc_type']

    def __str__(self):
        return self.doc_type

class RequiredDocument(models.Model):
    doc_application = models.ForeignKey(DocApplication, related_name='required_documents', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    file_link = models.CharField(max_length=500, blank=True)  # link to uploaded file

    @property
    def completed(self):
        return self.file_link != ''

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class DocWorkflow(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected')
    ]

    doc_application = models.ForeignKey(DocApplication, related_name='workflows', on_delete=models.CASCADE)
    task = models.OneToOneField(Task, on_delete=models.CASCADE)
    application_date = models.DateField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['application_date']

    def __str__(self):
        return self.task.name
