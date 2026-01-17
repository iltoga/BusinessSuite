from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customer_applications", "0003_remove_application_type"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="docapplication",
            index=models.Index(fields=["customer", "status"], name="docapp_customer_status_idx"),
        ),
    ]
