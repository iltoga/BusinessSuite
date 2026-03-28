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
        parser.add_argument(
            "--validate",
            action="store_true",
            help="Validate the generated schema using drf-spectacular checks",
        )
        parser.add_argument(
            "--fail-on-warn",
            action="store_true",
            help="Treat schema generation warnings as errors",
        )

    def handle(self, *args, **options):
        output = options["output"]
        validate = bool(options["validate"])
        fail_on_warn = bool(options["fail_on_warn"])
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
            spectacular_args = ["--file", str(out_path)]
            if validate:
                spectacular_args.append("--validate")
            if fail_on_warn:
                spectacular_args.append("--fail-on-warn")
            call_command("spectacular", *spectacular_args)
        except Exception as exc:
            raise CommandError(f"Error while running spectacular: {exc}")

        if out_path.exists():
            self.stdout.write(self.style.SUCCESS(f"Schema successfully written to {out_path}"))
        else:
            raise CommandError(f"Schema generation finished but file not found at {out_path}")
