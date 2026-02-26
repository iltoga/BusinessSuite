from django.db import migrations, models


def set_ai_validation_true_for_all_document_types(apps, schema_editor):
    DocumentType = apps.get_model("products", "DocumentType")
    DocumentType.objects.all().update(ai_validation=True)


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0007_product_validation_prompt"),
    ]

    operations = [
        migrations.RenameField(
            model_name="documenttype",
            old_name="has_ocr_check",
            new_name="ai_validation",
        ),
        migrations.AlterField(
            model_name="documenttype",
            name="ai_validation",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(
            set_ai_validation_true_for_all_document_types,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
