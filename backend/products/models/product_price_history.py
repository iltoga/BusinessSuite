from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone


class ProductPriceHistoryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(effective_to__isnull=True)


class ProductPriceHistory(models.Model):
    product = models.ForeignKey(
        "products.Product",
        related_name="price_history",
        on_delete=models.CASCADE,
    )
    base_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, default=Decimal("0.00"))
    retail_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, default=Decimal("0.00"))
    currency = models.CharField(max_length=3)
    effective_from = models.DateTimeField(db_index=True)
    effective_to = models.DateTimeField(blank=True, null=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = ProductPriceHistoryQuerySet.as_manager()

    class Meta:
        ordering = ["-effective_from", "-id"]
        indexes = [
            models.Index(fields=["product", "effective_from"], name="pricehist_prod_from_idx"),
            models.Index(fields=["product", "effective_to"], name="pricehist_prod_to_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(effective_to__isnull=True),
                name="pricehist_one_active_per_product",
            )
        ]

    def __str__(self) -> str:
        return f"{self.product.code} @ {self.effective_from:%Y-%m-%d %H:%M}"

    @classmethod
    def _invoice_day_bounds(cls, invoice_date) -> tuple[datetime, datetime] | tuple[None, None]:
        if not invoice_date:
            return None, None

        tz = timezone.get_current_timezone()
        invoice_day: date | None = None

        if isinstance(invoice_date, datetime):
            current = invoice_date
            if timezone.is_naive(current):
                current = timezone.make_aware(current, tz)
            invoice_day = timezone.localtime(current, tz).date()
        elif isinstance(invoice_date, date):
            invoice_day = invoice_date

        if invoice_day is None:
            return None, None

        start_dt = timezone.make_aware(datetime.combine(invoice_day, time.min), tz)
        return start_dt, start_dt + timedelta(days=1)

    @classmethod
    def for_invoice_date(cls, *, product_id: int, invoice_date) -> "ProductPriceHistory | None":
        if not product_id:
            return None

        start_dt, end_dt = cls._invoice_day_bounds(invoice_date)
        if start_dt is None or end_dt is None:
            return None

        return (
            cls.objects.filter(product_id=product_id, effective_from__lt=end_dt)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=start_dt))
            .order_by("-effective_from", "-id")
            .first()
        )

    @classmethod
    def resolve_for_invoice_date(cls, *, product_id: int, invoice_date) -> "ProductPriceHistory | None":
        if not product_id:
            return None

        history = cls.for_invoice_date(product_id=product_id, invoice_date=invoice_date)
        if history:
            return history

        start_dt, end_dt = cls._invoice_day_bounds(invoice_date)
        if start_dt is None or end_dt is None:
            return None

        closest_prior = (
            cls.objects.filter(product_id=product_id, effective_from__lt=end_dt)
            .order_by("-effective_from", "-id")
            .first()
        )
        if closest_prior:
            return closest_prior

        return cls.objects.filter(product_id=product_id).order_by("effective_from", "id").first()
