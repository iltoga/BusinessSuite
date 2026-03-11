from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.db.utils import OperationalError, ProgrammingError

from products.models import Product


def _default_dataset_path() -> Path:
    filename = "price_list_updated_jan_2026_import.json"
    candidates: list[Path] = []
    for ancestor in Path(__file__).resolve().parents:
        candidates.append(ancestor / "tmp" / filename)

    base_dir = Path(settings.BASE_DIR)
    candidates.extend(
        [
            base_dir / "tmp" / filename,
            base_dir.parent / "tmp" / filename,
            Path.cwd() / "tmp" / filename,
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate
    return candidates[0]


class Command(BaseCommand):
    help = (
        "Remove duplicate Products by name. Keeps the newest entries that match codes from the dataset file; "
        "if no dataset code matches a name, keeps the most recently updated record."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--path",
            default=str(_default_dataset_path()),
            help="Path to the structured JSON dataset to compare against.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the dedupe without deleting rows.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dataset_path = Path(options["path"]).expanduser().resolve()
        if not dataset_path.exists():
            raise CommandError(f"Dataset file not found: {dataset_path}")

        try:
            payload = json.loads(dataset_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {dataset_path}: {exc}") from exc

        product_rows = payload.get("products")
        if not isinstance(product_rows, list):
            raise CommandError("Dataset must contain a 'products' array.")

        dataset_codes = {
            str(row.get("code")).strip()
            for row in product_rows
            if isinstance(row, dict) and row.get("code")
        }

        if not dataset_codes:
            raise CommandError("Dataset contains no product codes to match against.")

        products = list(Product.objects.only("id", "name", "code", "updated_at"))
        by_name: dict[str, list[Product]] = {}
        for product in products:
            by_name.setdefault(product.name, []).append(product)

        deleted: list[tuple[str, str, str]] = []
        kept: list[tuple[str, str, str]] = []
        rewired: list[tuple[str, str, str]] = []

        try:
            with transaction.atomic():
                for name, group in sorted(by_name.items(), key=lambda item: item[0]):
                    if len(group) < 2:
                        continue

                    dataset_matches = [product for product in group if product.code in dataset_codes]
                    if dataset_matches:
                        newest_dataset = max(dataset_matches, key=lambda product: product.updated_at)
                        keep_ids = {newest_dataset.id}
                        kept.append((newest_dataset.code, newest_dataset.name, "dataset"))
                        delete_group = [product for product in group if product.id not in keep_ids]
                    else:
                        newest = max(group, key=lambda product: product.updated_at)
                        keep_ids = {newest.id}
                        kept.append((newest.code, newest.name, "latest"))
                        delete_group = [product for product in group if product.id not in keep_ids]

                    if delete_group:
                        for product in delete_group:
                            self._rewire_related(product, newest_dataset if dataset_matches else newest, rewired)
                            deleted.append((product.code, product.name, "duplicate"))
                        if not options["dry_run"]:
                            delete_ids = [product.id for product in delete_group]
                            Product.objects.filter(id__in=delete_ids).delete()

                if options["dry_run"]:
                    transaction.set_rollback(True)
                    self.stdout.write(self.style.WARNING("Dry run enabled: transaction rolled back."))
        except (ProgrammingError, OperationalError) as exc:
            raise CommandError("Database schema is not ready for product dedupe.") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Dedupe completed: kept={len(kept)}, deleted={len(deleted)}, "
                f"duplicate_names={sum(1 for group in by_name.values() if len(group) > 1)}"
            )
        )

        if kept:
            self.stdout.write(self.style.SUCCESS("Kept products (code - name - reason):"))
            for code, name, reason in sorted(kept, key=lambda item: item[0]):
                self.stdout.write(f"- {code} - {name} - {reason}")

        if deleted:
            self.stdout.write(self.style.SUCCESS("Deleted products (code - name):"))
            for code, name, _reason in sorted(deleted, key=lambda item: item[0]):
                self.stdout.write(f"- {code} - {name}")
        if rewired:
            self.stdout.write(self.style.SUCCESS("Rewired related records (from -> to):"))
            for from_code, to_code, relation in sorted(rewired, key=lambda item: item[0]):
                self.stdout.write(f"- {from_code} -> {to_code} ({relation})")

    def _rewire_related(self, source: Product, target: Product, rewired: list[tuple[str, str, str]]) -> None:
        if source.id == target.id:
            return
        for relation in source._meta.related_objects:
            if relation.many_to_many:
                continue
            related_model = relation.related_model
            field_name = relation.field.name
            if not field_name:
                continue
            try:
                updated = related_model._default_manager.filter(**{field_name: source}).update(**{field_name: target})
            except IntegrityError:
                continue
            if updated:
                relation_label = f"{related_model.__name__}.{field_name}"
                rewired.append((source.code, target.code, relation_label))
