from django.db import models
from django.conf import settings
from django.utils import timezone
from products.models import Product
from customers.models import Customer
from products.models import Product

class DocApplicationManager(models.Manager):
    def search_doc_applications(self, query):
        return self.filter(
            models.Q(product__name__icontains=query) |
            models.Q(product__code__icontains=query) |
            models.Q(product__product_type__icontains=query) |
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