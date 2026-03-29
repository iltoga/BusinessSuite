"""Core product model and pricing metadata used throughout the product app."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
from products.models.product_category import ProductCategory
from products.models.product_price_history import ProductPriceHistory


class ProductManager(models.Manager):
    def search_products(self, query):
        return self.filter(
            models.Q(name__icontains=query)
            | models.Q(code__icontains=query)
            | models.Q(description__icontains=query)
            | models.Q(product_category__product_type__icontains=query)
        )

    def filter_by_document_type_name(self, document_type_name: str):
        candidates = self.filter(
            models.Q(required_documents__icontains=document_type_name)
            | models.Q(optional_documents__icontains=document_type_name)
        )
        return [product for product in candidates if product.has_document_type(document_type_name)]


def default_product_currency() -> str:
    from core.services.app_setting_service import AppSettingService

    configured = str(AppSettingService.get_effective_raw("BASE_CURRENCY", "IDR") or "IDR").strip().upper()
    if configured.isalpha() and 2 <= len(configured) <= 3:
        return configured
    return "IDR"


class Product(models.Model):
    name = models.CharField(max_length=100, db_index=True)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    description = models.TextField(blank=True, db_index=True)
    product_category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name="products",
        db_index=True,
    )
    immigration_id = models.UUIDField(blank=True, null=True, db_index=True)
    base_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, default=Decimal("0.00"))
    retail_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, default=Decimal("0.00"))
    currency = models.CharField(
        max_length=3,
        default=default_product_currency,
        validators=[
            RegexValidator(
                regex=r"^[A-Za-z]{2,3}$",
                message="Currency must be a 2 or 3-letter code (e.g. IDR, USD, EUR).",
            )
        ],
    )
    # Validity in days
    validity = models.PositiveIntegerField(blank=True, null=True)
    # A comma-separated list of required documents
    required_documents = models.CharField(max_length=1024, blank=True)
    optional_documents = models.CharField(max_length=1024, blank=True)
    # Documents must be valid for this many days
    documents_min_validity = models.PositiveIntegerField(blank=True, null=True)
    # Number of days before stay permit expiration when the next visa application can be submitted.
    application_window_days = models.PositiveIntegerField(blank=True, null=True)
    # Optional AI system prompt injected during document validation for all applications using this product
    validation_prompt = models.TextField(blank=True)
    deprecated = models.BooleanField(default=False, db_index=True)
    # Flag to indicate if this product uses the customer app workflow, which requires additional processing and API calls.
    # Note: This is automatically computed based on the presence of configured documents and tasks, but stored as a denormalized field for easier querying and filtering.
    uses_customer_app_workflow = models.BooleanField(default=False, db_index=True)

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
        product_type = None
        if getattr(self, "product_category", None):
            product_type = self.product_category.product_type
        return {
            "code": self.code,
            "name": self.name,
            "base_price": self.base_price,
            "retail_price": self.retail_price,
            "currency": self.currency,
            "product_type": product_type,
        }

    def clean(self):
        super().clean()
        if self.retail_price is None:
            self.retail_price = self.base_price if self.base_price is not None else Decimal("0.00")
        if self.base_price is not None and self.retail_price < self.base_price:
            raise ValidationError({"retail_price": "Retail price must be greater than or equal to base price."})

    @property
    def required_document_names(self) -> list[str]:
        return [name.strip() for name in (self.required_documents or "").split(",") if name.strip()]

    @property
    def optional_document_names(self) -> list[str]:
        return [name.strip() for name in (self.optional_documents or "").split(",") if name.strip()]

    @property
    def all_document_names(self) -> list[str]:
        return [*self.required_document_names, *self.optional_document_names]

    def has_document_type(self, document_type_name: str) -> bool:
        return document_type_name in self.all_document_names

    @property
    def has_configured_documents(self) -> bool:
        return bool(self.required_document_names or self.optional_document_names)

    @property
    def has_configured_tasks(self) -> bool:
        if not self.pk:
            return False
        product_cache = getattr(self, "_prefetched_objects_cache", None) or {}
        if "tasks" in product_cache:
            return bool(product_cache["tasks"])
        tasks = getattr(self, "tasks", None)
        return bool(tasks and tasks.exists())

    def recompute_uses_customer_app_workflow(self) -> bool:
        return bool(self.has_configured_documents or self.has_configured_tasks)

    def has_deprecated_document_types(self) -> bool:
        from products.models.document_type import DocumentType

        doc_names = self.all_document_names
        if not doc_names:
            return False
        return DocumentType.objects.filter(name__in=doc_names, deprecated=True).exists()

    def sync_deprecated_status_from_documents(self) -> None:
        has_deprecated_documents = self.has_deprecated_document_types()
        if has_deprecated_documents:
            self.deprecated = True
            return

        # Keep explicit/manual deprecated toggles, but automatically clear
        # only when the previous deprecated state was document-driven.
        if self._state.adding or not self.pk:
            return
        try:
            previous = Product.objects.only(
                "id",
                "deprecated",
                "required_documents",
                "optional_documents",
            ).get(pk=self.pk)
        except Product.DoesNotExist:
            return

        if self.deprecated != previous.deprecated:
            return

        if previous.deprecated and previous.has_deprecated_document_types():
            self.deprecated = False

    def save(self, *args, **kwargs):
        if not getattr(self, "product_category_id", None):
            self.product_category = ProductCategory.get_default_for_type(self._product_type_hint)
        # Preserve legacy creates where base_price is provided but retail_price is omitted.
        if (
            self._state.adding
            and self.base_price not in (None, Decimal("0.00"))
            and self.retail_price == Decimal("0.00")
        ):
            self.retail_price = self.base_price
        elif self.retail_price is None:
            self.retail_price = self.base_price if self.base_price is not None else Decimal("0.00")
        if self.currency:
            self.currency = str(self.currency).strip().upper()
        else:
            self.currency = default_product_currency()
        self.sync_deprecated_status_from_documents()
        self.uses_customer_app_workflow = self.recompute_uses_customer_app_workflow()
        super().save(*args, **kwargs)
        self._sync_price_history(update_fields=kwargs.get("update_fields"))

    def _sync_price_history(self, *, update_fields=None) -> None:
        try:
            now = timezone.now()
            active = (
                ProductPriceHistory.objects.filter(product_id=self.pk, effective_to__isnull=True)
                .order_by("-effective_from")
                .first()
            )
            if update_fields is not None:
                tracked = {"base_price", "retail_price", "currency"}
                if not tracked.intersection(set(update_fields)) and active:
                    return
            if (
                active
                and active.base_price == self.base_price
                and active.retail_price == self.retail_price
                and active.currency == self.currency
            ):
                return

            if active:
                active.effective_to = now
                active.save(update_fields=["effective_to"])

            effective_from = self.created_at or now
            if active:
                effective_from = now

            ProductPriceHistory.objects.create(
                product_id=self.pk,
                base_price=self.base_price,
                retail_price=self.retail_price,
                currency=self.currency,
                effective_from=effective_from,
            )
        except (ProgrammingError, OperationalError):
            # Schema not ready (e.g. during migrations). Skip history sync.
            return

    def can_be_deleted(self) -> tuple[bool, str | None]:
        # Block deletion if directly referenced by invoice lines or by linked applications.
        invoice_apps = getattr(self, "invoice_applications", None)
        if invoice_apps is not None and invoice_apps.exists():
            return False, "Cannot delete product: related invoices exist."
        doc_apps = getattr(self, "doc_applications", None)
        if doc_apps is not None and doc_apps.filter(invoice_applications__isnull=False).exists():
            return False, "Cannot delete product: related invoices exist."
        # Alert if related applications/workflows exist
        if doc_apps is not None and doc_apps.exists():
            return True, "Warning: related applications/workflows exist."
        return True, None

    def delete(self, *args, **kwargs) -> tuple[int, dict[str, int]]:
        can_delete, msg = self.can_be_deleted()
        if not can_delete:
            from django.db.models import ProtectedError

            raise ProtectedError(str(msg or "Cannot delete product."), {self})
        return super().delete(*args, **kwargs)

    def __init__(self, *args, **kwargs):
        self._product_type_hint = kwargs.pop("product_type", None)
        super().__init__(*args, **kwargs)
