import json
import os

from django.core.management.base import BaseCommand

from products.models.product import Product


class Command(BaseCommand):
    help = "Populate the Product table from fixtures/products.json"

    def handle(self, *args, **options):
        fixture_path = os.path.join("fixtures", "products.json")
        if not os.path.exists(fixture_path):
            self.stderr.write(self.style.ERROR(f"File not found: {fixture_path}"))
            return

        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        created, updated = 0, 0
        for entry in data:
            fields = entry["fields"]
            pk = entry["pk"]
            obj, created_flag = Product.objects.update_or_create(pk=pk, defaults=fields)
            if created_flag:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Products loaded: {created} created, {updated} updated."))
