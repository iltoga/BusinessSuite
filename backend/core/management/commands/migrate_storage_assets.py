from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Run all cloud-storage migration steps: migrate local media files/directories to object storage "
        "and migrate OCR preview payloads from DB base64 to object storage."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be migrated without writing to object storage or DB.",
        )
        parser.add_argument(
            "--source-root",
            help="Local media root for file migration (forwarded to migrate_files_to_s3).",
        )
        parser.add_argument(
            "--extra-dir",
            action="append",
            dest="extra_dirs",
            default=None,
            help="Extra directory (relative to source root) for file migration. Can be used multiple times.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Batch size for OCR preview migration queryset iterator (default: 200).",
        )
        parser.add_argument(
            "--keep-b64",
            action="store_true",
            help="Keep b64_resized_image in OCRJob.result after preview migration.",
        )
        parser.add_argument(
            "--skip-files",
            action="store_true",
            help="Skip file/directory migration command.",
        )
        parser.add_argument(
            "--skip-ocr-previews",
            action="store_true",
            help="Skip OCR preview migration command.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        source_root = options.get("source_root")
        extra_dirs = list(options.get("extra_dirs") or [])
        batch_size = int(options.get("batch_size") or 200)
        keep_b64 = bool(options.get("keep_b64"))
        skip_files = bool(options.get("skip_files"))
        skip_ocr_previews = bool(options.get("skip_ocr_previews"))

        if skip_files and skip_ocr_previews:
            self.stdout.write("Nothing to do: both --skip-files and --skip-ocr-previews are set.")
            return

        if not skip_files:
            self.stdout.write("Running migrate_files_to_s3...")
            migrate_files_kwargs = {"dry_run": dry_run}
            if source_root:
                migrate_files_kwargs["source_root"] = source_root
            if extra_dirs:
                migrate_files_kwargs["extra_dirs"] = extra_dirs
            call_command("migrate_files_to_s3", stdout=self.stdout, stderr=self.stderr, **migrate_files_kwargs)
            self.stdout.write(self.style.SUCCESS("migrate_files_to_s3 completed."))

        if not skip_ocr_previews:
            self.stdout.write("Running migrate_ocr_previews_to_storage...")
            migrate_previews_kwargs = {
                "dry_run": dry_run,
                "batch_size": batch_size,
                "keep_b64": keep_b64,
            }
            call_command("migrate_ocr_previews_to_storage", stdout=self.stdout, stderr=self.stderr, **migrate_previews_kwargs)
            self.stdout.write(self.style.SUCCESS("migrate_ocr_previews_to_storage completed."))

        self.stdout.write(self.style.SUCCESS("migrate_storage_assets completed successfully."))
