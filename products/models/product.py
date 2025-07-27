from django.db import models


class ProductManager(models.Manager):
    def search_products(self, query):
        return self.filter(
            models.Q(name__icontains=query)
            | models.Q(code__icontains=query)
            | models.Q(description__icontains=query)
            | models.Q(product_type__icontains=query)
        )


class Product(models.Model):
    PRODUCT_TYPE_CHOICES = [
        ("visa", "Visa"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=100, db_index=True)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    description = models.TextField(blank=True, db_index=True)
    immigration_id = models.UUIDField(blank=True, null=True, db_index=True)
    base_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, default=0.00)
    product_type = models.CharField(max_length=50, choices=PRODUCT_TYPE_CHOICES, default="other", db_index=True)
    # Validity in days
    validity = models.PositiveIntegerField(blank=True, null=True)
    # A comma-separated list of required documents
    required_documents = models.CharField(max_length=1024, blank=True)
    optional_documents = models.CharField(max_length=1024, blank=True)
    # Documents must be valid for this many days
    documents_min_validity = models.PositiveIntegerField(blank=True, null=True)
    objects = ProductManager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.code + " - " + self.name

    def natural_key(self):
        """
        Returns a natural key that can be used to serialize this object.
        """
        return {
            "code": self.code,
            "name": self.name,
            "base_price": self.base_price,
            "product_type": self.product_type,
        }
