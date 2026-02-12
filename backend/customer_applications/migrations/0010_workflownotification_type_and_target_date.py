from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("customer_applications", "0009_docapplication_calendar_event_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflownotification",
            name="notification_type",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="workflownotification",
            name="target_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="workflownotification",
            constraint=models.UniqueConstraint(
                condition=Q(("notification_type", "due_tomorrow"), ("target_date__isnull", False)),
                fields=("doc_application", "channel", "notification_type", "target_date"),
                name="uniq_due_tomorrow_notification_per_channel",
            ),
        ),
    ]
