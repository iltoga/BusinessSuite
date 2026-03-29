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

from django.core import serializers
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Imports a Django model from a JSON file"

    def add_arguments(self, parser):
        parser.add_argument("input_file", type=str)

    def handle(self, *args, **options):
        input_file = options["input_file"]

        with open(input_file, "r") as f:
            for obj in serializers.deserialize("json", f):
                obj.save()

        self.stdout.write(self.style.SUCCESS('Successfully imported data from "%s"' % input_file))
