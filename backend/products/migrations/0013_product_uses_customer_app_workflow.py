from django.db import migrations, models


def _split_document_names(raw_value):
    if not raw_value:
        return []
    return [name.strip() for name in str(raw_value).split(",") if name and name.strip()]


def backfill_uses_customer_app_workflow(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    Task = apps.get_model("products", "Task")

    product_ids_with_tasks = set(Task.objects.values_list("product_id", flat=True))

    updates = []
    for product in Product.objects.all().only("id", "required_documents", "optional_documents", "uses_customer_app_workflow"):
        has_documents = bool(
            _split_document_names(product.required_documents)
            or _split_document_names(product.optional_documents)
        )
        desired = has_documents or (product.id in product_ids_with_tasks)
        if product.uses_customer_app_workflow != desired:
            product.uses_customer_app_workflow = desired
            updates.append(product)

    if updates:
        Product.objects.bulk_update(updates, ["uses_customer_app_workflow"])


def reverse_backfill_uses_customer_app_workflow(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    Product.objects.all().update(uses_customer_app_workflow=False)


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0012_documenttype_ai_structured_output"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="uses_customer_app_workflow",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.RunPython(
            backfill_uses_customer_app_workflow,
            reverse_backfill_uses_customer_app_workflow,
        ),
    ]
