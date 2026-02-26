from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("customer_applications", "0014_document_ai_validation_fields"),
    ]

    operations = [
        migrations.RenameField(
            model_name="document",
            old_name="ocr_check",
            new_name="ai_validation",
        ),
    ]
