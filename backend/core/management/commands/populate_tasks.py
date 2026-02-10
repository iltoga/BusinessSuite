import json
import os

from django.core.management.base import BaseCommand

from products.models.product import Product
from products.models.task import Task


class Command(BaseCommand):
    help = "Populate the Task table from fixtures/tasks.json"

    def handle(self, *args, **options):
        fixture_path = os.path.join("fixtures", "tasks.json")
        if not os.path.exists(fixture_path):
            self.stderr.write(self.style.ERROR(f"File not found: {fixture_path}"))
            return

        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        created, updated = 0, 0
        for entry in data:
            fields = entry["fields"]
            pk = entry["pk"]

            # Handle the foreign key relationship for product
            product_id = fields.pop("product")
            try:
                product = Product.objects.get(pk=product_id)
                fields["product"] = product
            except Product.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Product with ID {product_id} does not exist. Skipping task {pk}."))
                continue

            obj, created_flag = Task.objects.update_or_create(pk=pk, defaults=fields)
            if created_flag:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Tasks loaded: {created} created, {updated} updated."))
