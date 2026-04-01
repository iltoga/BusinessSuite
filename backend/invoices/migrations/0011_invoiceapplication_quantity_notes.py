"""Add quantity and notes to invoice application rows."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("invoices", "0010_add_overpaid_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceapplication",
            name="notes",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="invoiceapplication",
            name="quantity",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddConstraint(
            model_name="invoiceapplication",
            constraint=models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="invoiceapp_quantity_gte_1",
            ),
        ),
    ]
