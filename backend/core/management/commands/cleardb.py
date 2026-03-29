"""
FILE_ROLE: Django management command for the core app.

KEY_COMPONENTS:
- Command: Module symbol.

INTERACTIONS:
- Depends on: core models, Django migration/management machinery, and related app services imported by this module.

AI_GUIDELINES:
- Keep command logic thin and delegate real work to services when possible.
- Keep migrations schema-only and reversible; do not add runtime business logic here.
"""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    """
    A Django management command that completely wipes the database clean.

    This command drops the public schema and recreates it,
    effectively wiping all data from the database.

    Usage:
        python manage.py cleardb

    """

    help = "Completely wipes the database clean."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA public CASCADE;")
            cursor.execute("CREATE SCHEMA public;")

        self.stdout.write(self.style.SUCCESS("Database cleared successfully."))
