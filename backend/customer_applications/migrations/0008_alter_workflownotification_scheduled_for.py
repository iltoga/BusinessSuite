from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customer_applications", "0007_alter_workflownotification_recipient"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workflownotification",
            name="scheduled_for",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
