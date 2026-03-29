"""Management command for extracting AI structured output data."""

import json

from django.core.management.base import BaseCommand
from products.management.commands.ai_structured_output_utils import format_output, generate_ai_structured_output
from products.models.document_type import DocumentType


class Command(BaseCommand):
    help = (
        "Generate a preview of the JSON structure that the AI should extract from each "
        "DocumentType based on its validation_rule_ai_positive, name, and description. "
        "Output is printed to stdout and not saved."
    )

    def handle(self, *args, **options):
        # iterate in database order
        for dt in DocumentType.objects.all():
            structured = generate_ai_structured_output(dt)
            self.stdout.write(self.style.MIGRATE_HEADING(f"{dt.name}"))
            self.stdout.write(format_output(structured))
            self.stdout.write("\n")
