from django.db import migrations, models
import django.db.models.deletion


def create_product_categories(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    ProductCategory = apps.get_model("products", "ProductCategory")

    visa_category, _ = ProductCategory.objects.get_or_create(
        name="Visa",
        product_type="visa",
        defaults={"description": ""},
    )
    other_category, _ = ProductCategory.objects.get_or_create(
        name="Other",
        product_type="other",
        defaults={"description": ""},
    )

    Product.objects.filter(product_type="visa").update(product_category_id=visa_category.id)
    Product.objects.filter(product_type="other").update(product_category_id=other_category.id)
    Product.objects.exclude(product_type__in=["visa", "other"]).update(product_category_id=other_category.id)


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0015_documenttype_auto_generation"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(db_index=True, max_length=100, unique=True)),
                ("product_type", models.CharField(choices=[("visa", "Visa"), ("other", "Other")], db_index=True, max_length=50)),
                ("description", models.TextField(blank=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="product",
            name="product_category",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products",
                to="products.productcategory",
            ),
        ),
        migrations.RunPython(create_product_categories, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="product",
            name="product_type",
        ),
        migrations.AlterField(
            model_name="product",
            name="product_category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products",
                to="products.productcategory",
                db_index=True,
            ),
        ),
    ]
