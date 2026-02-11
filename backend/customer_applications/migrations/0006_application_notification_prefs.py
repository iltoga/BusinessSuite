from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customer_applications", "0005_application_deadlines_and_notifications"),
    ]

    operations = [
        migrations.AddField(
            model_name="docapplication",
            name="notify_customer_too",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="docapplication",
            name="notification_channel",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="workflownotification",
            name="notify_at",
            field=models.DateTimeField(blank=True, null=True, db_index=True),
        ),
    ]
