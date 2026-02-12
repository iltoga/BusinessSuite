from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customer_applications", "0008_alter_workflownotification_scheduled_for"),
    ]

    operations = [
        migrations.AddField(
            model_name="docapplication",
            name="calendar_event_id",
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
    ]
