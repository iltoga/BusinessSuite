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
