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
