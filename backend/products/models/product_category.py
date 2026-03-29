"""Product category model used to group product and document type records."""

from __future__ import annotations

from django.db import models


class ProductCategory(models.Model):
    PRODUCT_TYPE_CHOICES = [
        ("visa", "Visa"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=100, unique=True, db_index=True)
    product_type = models.CharField(max_length=50, choices=PRODUCT_TYPE_CHOICES, db_index=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def default_names(cls) -> dict[str, str]:
        return {
            "visa": "Visa",
            "other": "Other",
        }

    @classmethod
    def get_default_for_type(cls, product_type: str | None):
        normalized = (product_type or "").strip().lower() or "other"
        if normalized not in cls.default_names():
            normalized = "other"
        name = cls.default_names()[normalized]
        category, _ = cls.objects.get_or_create(
            product_type=normalized,
            name=name,
            defaults={"description": ""},
        )
        return category
