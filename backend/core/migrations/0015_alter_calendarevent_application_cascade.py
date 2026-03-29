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
        ("core", "0014_calendarevent"),
    ]

    operations = [
        migrations.AlterField(
            model_name="calendarevent",
            name="application",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="calendar_events",
                to="customer_applications.docapplication",
            ),
        ),
    ]
