"""Management command for updating AI structured output settings."""

import json

from django.core.management.base import BaseCommand
from products.management.commands.ai_structured_output_utils import format_output, generate_ai_structured_output
from products.models.document_type import DocumentType


class Command(BaseCommand):
    help = (
        "Compute the AI-structured-output JSON for each DocumentType and "
        "persist it in the ``ai_structured_output`` field. Only types whose "
        "value changes will be saved."
    )

    def handle(self, *args, **options):
        updated = 0
        total = 0
        for dt in DocumentType.objects.all():
            total += 1
            structured = generate_ai_structured_output(dt)
            json_str = json.dumps(structured, ensure_ascii=False)
            if dt.ai_structured_output != json_str:
                dt.ai_structured_output = json_str
                dt.save(update_fields=["ai_structured_output"])
                updated += 1
                self.stdout.write(self.style.SUCCESS(f"Updated {dt.name}"))
            else:
                self.stdout.write(f"No change for {dt.name}")
        self.stdout.write(self.style.SUCCESS(f"Processed {total} document types ({updated} updated)"))
