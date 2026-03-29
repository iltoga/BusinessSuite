"""
FILE_ROLE: Django migration for the core app.

KEY_COMPONENTS:
- Migration: Module symbol.

INTERACTIONS:
- Depends on: core app schema/runtime machinery and adjacent services imported by this module.

AI_GUIDELINES:
- Keep command logic thin and delegate real work to services when possible.
- Keep migrations schema-only and reversible; do not add runtime business logic here.
"""

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
