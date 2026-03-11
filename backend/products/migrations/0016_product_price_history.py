from __future__ import annotations

from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion
from django.utils import timezone


def create_initial_price_history(apps, schema_editor) -> None:
    Product = apps.get_model("products", "Product")
    ProductPriceHistory = apps.get_model("products", "ProductPriceHistory")
    db = schema_editor.connection.alias

    existing = set(ProductPriceHistory.objects.using(db).values_list("product_id", flat=True))
    now = timezone.now()

    for product in (
        Product.objects.using(db)
        .all()
        .only("id", "base_price", "retail_price", "currency", "created_at")
        .iterator()
    ):
        if product.id in existing:
            continue
        ProductPriceHistory.objects.using(db).create(
            product_id=product.id,
            base_price=product.base_price,
            retail_price=product.retail_price,
            currency=product.currency,
            effective_from=product.created_at or now,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0015_documenttype_auto_generation"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductPriceHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("base_price", models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12, null=True)),
                (
                    "retail_price",
                    models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=12, null=True),
                ),
                ("currency", models.CharField(max_length=3)),
                ("effective_from", models.DateTimeField(db_index=True)),
                ("effective_to", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_history",
                        to="products.product",
                    ),
                ),
            ],
            options={
                "ordering": ["-effective_from", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="productpricehistory",
            index=models.Index(fields=["product", "effective_from"], name="pricehist_prod_from_idx"),
        ),
        migrations.AddIndex(
            model_name="productpricehistory",
            index=models.Index(fields=["product", "effective_to"], name="pricehist_prod_to_idx"),
        ),
        migrations.AddConstraint(
            model_name="productpricehistory",
            constraint=models.UniqueConstraint(
                fields=("product",),
                condition=Q(("effective_to__isnull", True)),
                name="pricehist_one_active_per_product",
            ),
        ),
        migrations.RunPython(create_initial_price_history, migrations.RunPython.noop),
    ]

