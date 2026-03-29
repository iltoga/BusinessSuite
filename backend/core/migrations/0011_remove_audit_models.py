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

# Generated migration to remove legacy audit models (CRUDEvent, LoginEvent, RequestEvent)
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_alter_usersettings_options_crudevent_loginevent_and_more"),
    ]

    operations = [
        migrations.DeleteModel(name="CRUDEvent"),
        migrations.DeleteModel(name="LoginEvent"),
        migrations.DeleteModel(name="RequestEvent"),
    ]
