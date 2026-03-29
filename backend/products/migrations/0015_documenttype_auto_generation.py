"""Add automatic document generation flags to document types."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0014_product_currency"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttype",
            name="auto_generation",
            field=models.BooleanField(
                default=False,
                help_text="Whether this document type exposes a system-provided automatic generation/upload action.",
            ),
        ),
        migrations.RunPython(
            code=lambda apps, schema_editor: apps.get_model("products", "DocumentType")
            .objects.filter(name__in=["KTP Sponsor", "Surat Permohonan dan Jaminan"])
            .update(auto_generation=True),
            reverse_code=lambda apps, schema_editor: apps.get_model("products", "DocumentType")
            .objects.filter(name__in=["KTP Sponsor", "Surat Permohonan dan Jaminan"])
            .update(auto_generation=False),
        ),
    ]
