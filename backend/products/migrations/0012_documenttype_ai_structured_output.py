"""Add structured AI output fields for document type processing."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0011_documenttype_expiring_threshold_days"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttype",
            name="ai_structured_output",
            field=models.TextField(blank=True),
        ),
    ]
