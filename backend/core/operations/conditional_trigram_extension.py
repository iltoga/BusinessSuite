"""
FILE_ROLE: Provides a conditional PostgreSQL trigram extension migration helper.

KEY_COMPONENTS:
- ConditionalTrigramExtension: RunSQL helper that enables pg_trgm unless the database is SQLite.

INTERACTIONS:
- Depends on: django.db.connections, django.db.migrations.

AI_GUIDELINES:
- Keep this helper migration-safe and database-vendor aware.
- Do not add unrelated schema behavior here; the class should stay narrowly focused on the pg_trgm extension.
"""

from django.db import connections, migrations


class ConditionalTrigramExtension(migrations.RunSQL):
    def __init__(self):
        super().__init__(
            sql="CREATE EXTENSION IF NOT EXISTS pg_trgm;",
            reverse_sql="",
        )

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        database_alias = schema_editor.connection.alias
        if connections[database_alias].vendor != "sqlite":
            super().database_forwards(app_label, schema_editor, from_state, to_state)
