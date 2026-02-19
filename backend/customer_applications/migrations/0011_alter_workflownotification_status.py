from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customer_applications", "0010_workflownotification_type_and_target_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workflownotification",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("sent", "Sent"),
                    ("delivered", "Delivered"),
                    ("read", "Read"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
    ]
