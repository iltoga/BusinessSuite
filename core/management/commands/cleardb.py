from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Completely wipes the database clean."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA public CASCADE;")
            cursor.execute("CREATE SCHEMA public;")

        self.stdout.write(self.style.SUCCESS("Database cleared successfully."))
