from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_add_delivery_channel_to_calendarreminder"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendarreminder",
            name="delivery_device_label",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="calendarreminder",
            name="read_device_label",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
