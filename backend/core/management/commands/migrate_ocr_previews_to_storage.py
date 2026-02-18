from django.core.management.base import BaseCommand

from core.models import OCRJob
from core.services.ocr_preview_storage import upload_ocr_preview_from_base64


class Command(BaseCommand):
    help = (
        "Migrate OCRJob preview images stored as base64 in result JSON to object storage "
        "and replace them with preview_storage_path."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be migrated without writing changes to DB/storage.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Queryset iterator batch size (default: 200).",
        )
        parser.add_argument(
            "--keep-b64",
            action="store_true",
            help="Keep b64_resized_image in result after migration (default removes it).",
        )

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        batch_size = int(options["batch_size"] or 200)
        keep_b64 = bool(options["keep_b64"])

        counters = {
            "checked": 0,
            "migrated": 0,
            "would_migrate": 0,
            "skipped_no_b64": 0,
            "skipped_has_storage_path": 0,
            "errors": 0,
        }

        queryset = OCRJob.objects.exclude(result__isnull=True).only("id", "result", "updated_at").order_by("created_at")

        for job in queryset.iterator(chunk_size=batch_size):
            counters["checked"] += 1

            result = job.result if isinstance(job.result, dict) else {}
            b64_payload = result.get("b64_resized_image") or result.get("b64ResizedImage")
            if not b64_payload:
                counters["skipped_no_b64"] += 1
                continue

            if result.get("preview_storage_path"):
                counters["skipped_has_storage_path"] += 1
                continue

            if dry_run:
                counters["would_migrate"] += 1
                self.stdout.write(f"[DRY RUN] Would migrate OCRJob {job.id}")
                continue

            try:
                storage_path = upload_ocr_preview_from_base64(
                    job_id=str(job.id),
                    payload=b64_payload,
                    extension="png",
                    overwrite=True,
                )
            except Exception as exc:
                counters["errors"] += 1
                self.stderr.write(f"[ERROR] OCRJob {job.id}: {exc}")
                continue

            result["preview_storage_path"] = storage_path
            result["preview_mime_type"] = "image/png"
            if not keep_b64:
                result.pop("b64_resized_image", None)
                result.pop("b64ResizedImage", None)

            try:
                job.result = result
                job.save(update_fields=["result", "updated_at"])
            except Exception as exc:
                counters["errors"] += 1
                self.stderr.write(f"[ERROR] Failed to save OCRJob {job.id}: {exc}")
                continue

            counters["migrated"] += 1
            self.stdout.write(self.style.SUCCESS(f"[MIGRATED] OCRJob {job.id} -> {storage_path}"))

        summary = (
            "OCR preview migration summary: "
            f"checked={counters['checked']}, "
            f"migrated={counters['migrated']}, "
            f"would_migrate={counters['would_migrate']}, "
            f"skipped_no_b64={counters['skipped_no_b64']}, "
            f"skipped_has_storage_path={counters['skipped_has_storage_path']}, "
            f"errors={counters['errors']}"
        )
        if counters["errors"]:
            self.stdout.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
