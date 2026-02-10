"""
Migration adding birth_place field to Customer model.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0006_add_passport_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="birth_place",
            field=models.CharField(max_length=100, null=True, blank=True),
        ),
    ]
