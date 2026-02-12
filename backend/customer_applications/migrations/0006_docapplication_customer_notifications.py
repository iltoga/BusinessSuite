from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customer_applications", "0005_application_deadlines_and_notifications"),
    ]

    operations = [
        migrations.AddField(
            model_name="docapplication",
            name="notify_customer_channel",
            field=models.CharField(
                blank=True,
                choices=[("email", "Email"), ("whatsapp", "WhatsApp")],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="docapplication",
            name="notify_customer_too",
            field=models.BooleanField(default=False),
        ),
    ]
