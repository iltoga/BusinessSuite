"""
Migration adding passport fields to Customer model.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0005_alter_customer_unique_together"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="passport_number",
            field=models.CharField(max_length=50, null=True, blank=True, db_index=True),
        ),
        migrations.AddField(
            model_name="customer",
            name="passport_issue_date",
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="customer",
            name="passport_expiration_date",
            field=models.DateField(null=True, blank=True),
        ),
    ]
