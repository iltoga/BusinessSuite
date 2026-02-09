from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, call_command
from django.core.management.base import CommandError


class Command(BaseCommand):
    help = "Generate OpenAPI schema using drf-spectacular and write it to the frontend directory (default: schema.yaml)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            "-o",
            default="schema.yaml",
            help="Output path for the generated schema (relative to project base dir)",
        )

    def handle(self, *args, **options):
        output = options["output"]
        # settings.BASE_DIR points to the Django project dir (business_suite/). We want
        # the repository root (one level up) so default frontend/ resolves to the repo-level frontend folder.
        project_root = Path(settings.BASE_DIR).parent
        out_path = (project_root / output).resolve()
        out_dir = out_path.parent
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise CommandError(f"Failed to create output directory {out_dir}: {exc}")

        self.stdout.write(f"Generating OpenAPI schema to {out_path} ...")
        try:
            # Use drf-spectacular management command to write the schema (YAML inferred from file extension)
            call_command("spectacular", "--file", str(out_path))
        except Exception as exc:
            raise CommandError(f"Error while running spectacular: {exc}")

        if out_path.exists():
            self.stdout.write(self.style.SUCCESS(f"Schema successfully written to {out_path}"))
        else:
            raise CommandError(f"Schema generation finished but file not found at {out_path}")
