from django.db import models

class ProductManager(models.Manager):
    def search_products(self, query):
        return self.filter(
            models.Q(name__icontains=query) |
            models.Q(code__icontains=query) |
            models.Q(description__icontains=query) |
            models.Q(product_type__icontains=query)
        )

class Product(models.Model):
    PRODUCT_TYPE_CHOICES = [
        ('visa', 'Visa'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=100, db_index=True)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    description = models.TextField(blank=True, db_index=True)
    base_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, default=0.00)
    product_type = models.CharField(max_length=50, choices=PRODUCT_TYPE_CHOICES, default='other', db_index=True)
    validity = models.PositiveIntegerField(blank=True, null=True)  # Validity in days
    required_documents = models.CharField(max_length=1024, blank=True)  # A comma-separated list of required documents
    documents_min_validity = models.PositiveIntegerField(blank=True, null=True)  # Documents must be valid for this many days
    objects = ProductManager()

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['name'], name='product_name_idx'),
            models.Index(fields=['code'], name='product_code_idx'),
            models.Index(fields=['description'], name='product_description_idx'),
            models.Index(fields=['product_type'], name='product_type_idx'),
        ]

    def __str__(self):
        return self.code
