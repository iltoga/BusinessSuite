from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
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
    retail_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, default=0.00)
    product_type = models.CharField(max_length=50, choices=PRODUCT_TYPE_CHOICES, default="other", db_index=True)
    # Validity in days
    validity = models.PositiveIntegerField(blank=True, null=True)
    # A comma-separated list of required documents
    required_documents = models.CharField(max_length=1024, blank=True)
    optional_documents = models.CharField(max_length=1024, blank=True)
    # Documents must be valid for this many days
    documents_min_validity = models.PositiveIntegerField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_by_product",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_by_product",
        null=True,
        blank=True,
    )

    objects = ProductManager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(base_price__isnull=True) | models.Q(retail_price__gte=models.F("base_price")),
                name="product_retail_price_gte_base_price",
            ),
        ]

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
            "retail_price": self.retail_price,
            "product_type": self.product_type,
        }

    def clean(self):
        super().clean()
        if self.retail_price is None:
            self.retail_price = self.base_price if self.base_price is not None else Decimal("0.00")
        if self.base_price is not None and self.retail_price < self.base_price:
            raise ValidationError({"retail_price": "Retail price must be greater than or equal to base price."})

    def save(self, *args, **kwargs):
        # Preserve legacy creates where base_price is provided but retail_price is omitted.
        if self._state.adding and self.base_price not in (None, Decimal("0.00")) and self.retail_price == Decimal(
            "0.00"
        ):
            self.retail_price = self.base_price
        elif self.retail_price is None:
            self.retail_price = self.base_price if self.base_price is not None else Decimal("0.00")
        super().save(*args, **kwargs)

    def can_be_deleted(self):
        # Block deletion if related invoices exist
        if (
            hasattr(self, "doc_applications")
            and self.doc_applications.filter(invoice_applications__isnull=False).exists()
        ):
            return False, "Cannot delete product: related invoices exist."
        # Alert if related applications/workflows exist
        if hasattr(self, "doc_applications") and self.doc_applications.exists():
            return True, "Warning: related applications/workflows exist."
        return True, None

    def delete(self, *args, **kwargs):
        can_delete, msg = self.can_be_deleted()
        if not can_delete:
            from django.db.models import ProtectedError

            raise ProtectedError(msg, self)
        super().delete(*args, **kwargs)
