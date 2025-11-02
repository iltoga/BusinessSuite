"""
Management command to reset the PostgreSQL sequence for products_product table.
This fixes the "duplicate key value violates unique constraint" error.

Usage:
    python manage.py reset_product_sequence
"""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Reset the PostgreSQL sequence for products_product table to match current max ID"

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # Get the current max ID from the products_product table
            cursor.execute("SELECT MAX(id) FROM products_product;")
            max_id = cursor.fetchone()[0] or 0

            # Reset the sequence to max_id + 1
            next_id = max_id + 1
            cursor.execute(f"SELECT setval('products_product_id_seq', {next_id}, false);")

            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Successfully reset products_product_id_seq to {next_id} (current max ID: {max_id})"
                )
            )

            # Verify the sequence
            cursor.execute("SELECT last_value FROM products_product_id_seq;")
            last_value = cursor.fetchone()[0]
            self.stdout.write(self.style.SUCCESS(f"✓ Sequence last_value is now: {last_value}"))
