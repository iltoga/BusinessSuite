"""Add the runtime override flag to application settings.

This migration marks whether a setting is supplied dynamically at runtime or
persisted as the default configuration.
"""

from django.db import migrations, models


def add_is_runtime_override_if_missing(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    table_name = AppSetting._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }

    if "is_runtime_override" in columns:
        return

    field = models.BooleanField(default=False)
    field.set_attributes_from_name("is_runtime_override")
    schema_editor.add_field(AppSetting, field)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0028_asyncjob_core_asyncjob_guard_idx_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_is_runtime_override_if_missing,
                    reverse_code=migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="appsetting",
                    name="is_runtime_override",
                    field=models.BooleanField(default=False),
                ),
            ],
        ),
    ]
