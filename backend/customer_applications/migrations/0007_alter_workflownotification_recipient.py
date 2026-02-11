from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customer_applications", "0006_docapplication_customer_notifications"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workflownotification",
            name="recipient",
            field=models.CharField(max_length=255),
        ),
    ]
