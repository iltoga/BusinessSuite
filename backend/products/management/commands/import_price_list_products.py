from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from products.models import Product, ProductCategory


MANUAL_CATEGORY_BY_CODE: dict[str, str] = {
    "AIRPORT": "Other",
    "BANK_FEE": "Other",
    "GRAB": "Other",
    "Notary Fee": "Other",
    "Speed up Process": "Other",
    "Stamp": "Other",
    "TELKOMSEL": "Other",
    "LKPM-1": "Other",
    "LKPM-12": "Other",
    "N-PMA": "Other",
    "NEW PMA": "Other",
    "NPMA": "Other",
    "P-NPWP": "Other",
    "PCG PMA": "Other",
    "PT-PMA": "Other",
    "RPT-FIN": "Other",
    "RPT-TAX": "Other",
    "SIM-A": "Other",
    "SIM-C": "Other",
    "SKTT": "Other",
    "SPT": "Other",
    "SPT 3": "Other",
    "SPT-1": "Other",
    "SPT-3": "Other",
    "SPT-IMTA": "Other",
    "SRV-Konsul": "Other",
}


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
        "Import a structured price-list JSON file into ProductCategory and Product using upsert mode. "
        "Categories are matched by unique name and products by code."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--path",
            default=str(_default_dataset_path()),
            help="Path to the structured JSON dataset to import.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and simulate the import without committing database changes.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dataset_path = self._resolve_path(options["path"])
        if not dataset_path.exists():
            raise CommandError(f"Dataset file not found: {dataset_path}")

        try:
            payload = json.loads(dataset_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {dataset_path}: {exc}") from exc

        category_rows = payload.get("product_categories")
        product_rows = payload.get("products")
        if not isinstance(category_rows, list) or not isinstance(product_rows, list):
            raise CommandError("Dataset must contain 'product_categories' and 'products' arrays.")

        source = payload.get("source") or {}
        source_warning = source.get("warning")
        if source_warning:
            self.stdout.write(self.style.WARNING(f"Source warning: {source_warning}"))

        created_categories = 0
        updated_categories = 0
        created_products = 0
        updated_products = 0
        unchanged_products = 0
        created_product_list: list[tuple[str, str]] = []
        updated_product_list: list[tuple[str, str]] = []
        unchanged_product_list: list[tuple[str, str]] = []
        missing_in_dataset: list[tuple[str, str, str, str]] = []
        manually_mapped: list[tuple[str, str, str]] = []
        deprecated_products: list[tuple[str, str]] = []
        dataset_codes: set[str] = set()

        duplicate_codes = self._find_duplicates(row.get("code") for row in product_rows if isinstance(row, dict))
        if duplicate_codes:
            duplicates = ", ".join(sorted(duplicate_codes))
            raise CommandError(f"Dataset contains duplicate product codes: {duplicates}")

        try:
            with transaction.atomic():
                category_map: dict[str, ProductCategory] = {}
                for row in category_rows:
                    if not isinstance(row, dict):
                        raise CommandError("Each product category entry must be an object.")

                    name = self._require_string(row, "name")
                    product_type = self._require_string(row, "product_type").lower()
                    if product_type not in {choice for choice, _ in ProductCategory.PRODUCT_TYPE_CHOICES}:
                        raise CommandError(f"Invalid product_type '{product_type}' for category '{name}'.")

                    defaults = {
                        "product_type": product_type,
                        "description": str(row.get("description") or ""),
                    }
                    category, created = ProductCategory.objects.update_or_create(name=name, defaults=defaults)
                    category_map[name] = category
                    if created:
                        created_categories += 1
                    else:
                        updated_categories += 1

                for row in product_rows:
                    if not isinstance(row, dict):
                        raise CommandError("Each product entry must be an object.")

                    code = self._require_string(row, "code")
                    dataset_codes.add(code)
                    category_name = self._require_string(row, "product_category")
                    category = category_map.get(category_name)
                    if category is None:
                        raise CommandError(f"Product '{code}' references unknown category '{category_name}'.")

                    defaults = {
                        "name": self._require_string(row, "name"),
                        "description": str(row.get("description") or ""),
                        "product_category": category,
                        "base_price": self._to_decimal(row.get("base_price")),
                        "retail_price": self._to_decimal(row.get("retail_price")),
                        "currency": (str(row.get("currency") or "IDR").strip().upper() or "IDR"),
                        "validity": self._to_optional_int(row.get("validity")),
                        "required_documents": str(row.get("required_documents") or ""),
                        "optional_documents": str(row.get("optional_documents") or ""),
                        "documents_min_validity": self._to_optional_int(row.get("documents_min_validity")),
                        "application_window_days": self._to_optional_int(row.get("application_window_days")),
                        "validation_prompt": str(row.get("validation_prompt") or ""),
                        "deprecated": bool(row.get("deprecated", False)),
                    }

                    product = Product.objects.filter(code=code).first()
                    if product is None:
                        product = Product(code=code, **defaults)
                        product.full_clean()
                        product.save()
                        created_products += 1
                        created_product_list.append((product.code, product.name))
                        continue

                    if not self._product_changed(product, defaults):
                        unchanged_products += 1
                        unchanged_product_list.append((product.code, product.name))
                        continue

                    for field_name, value in defaults.items():
                        setattr(product, field_name, value)
                    product.full_clean()
                    product.save()
                    updated_products += 1
                    updated_product_list.append((product.code, product.name))

                if dataset_codes:
                    for product in (
                        Product.objects.exclude(code__in=dataset_codes)
                        .select_related("product_category")
                        .only("code", "name", "product_category__name", "product_category__product_type")
                    ):
                        category_name = ""
                        category_type = ""
                        if product.product_category_id:
                            category_name = product.product_category.name
                            category_type = product.product_category.product_type
                        missing_in_dataset.append((product.code, product.name, category_name, category_type))

                        if not product.deprecated:
                            product.deprecated = True
                            product.full_clean()
                            product.save()
                            deprecated_products.append((product.code, product.name))

                        manual_category_name = MANUAL_CATEGORY_BY_CODE.get(product.code)
                        if not manual_category_name:
                            continue

                        manual_category = category_map.get(manual_category_name)
                        if manual_category is None:
                            manual_category = ProductCategory.get_default_for_type(manual_category_name)
                        if product.product_category_id != manual_category.id:
                            product.product_category = manual_category
                            product.full_clean()
                            product.save()
                            manually_mapped.append((product.code, product.name, manual_category.name))

                if options["dry_run"]:
                    transaction.set_rollback(True)
                    self.stdout.write(self.style.WARNING("Dry run enabled: transaction rolled back."))
        except (ProgrammingError, OperationalError) as exc:
            raise CommandError(
                "Database schema is not ready for ProductCategory imports. "
                "Run the product migrations first, then retry."
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Import completed: "
                f"categories(created={created_categories}, updated={updated_categories}), "
                f"products(created={created_products}, updated={updated_products}, unchanged={unchanged_products})"
            )
        )

        if updated_product_list:
            self.stdout.write(self.style.SUCCESS("Updated products (code - name):"))
            for code, name in sorted(updated_product_list, key=lambda item: item[0]):
                self.stdout.write(f"- {code} - {name}")
        if created_product_list:
            self.stdout.write(self.style.SUCCESS("Created products (code - name):"))
            for code, name in sorted(created_product_list, key=lambda item: item[0]):
                self.stdout.write(f"- {code} - {name}")
        if unchanged_product_list:
            self.stdout.write(self.style.SUCCESS("Unchanged products (code - name):"))
            for code, name in sorted(unchanged_product_list, key=lambda item: item[0]):
                self.stdout.write(f"- {code} - {name}")
        if missing_in_dataset:
            self.stdout.write(
                self.style.SUCCESS(
                    "Existing DB products not in dataset (potential manual mapping: code - name - category [type]):"
                )
            )
            for code, name, category_name, category_type in sorted(missing_in_dataset, key=lambda item: item[0]):
                category_label = category_name or "Uncategorized"
                type_label = category_type or "unknown"
                self.stdout.write(f"- {code} - {name} - {category_label} [{type_label}]")
        if deprecated_products:
            self.stdout.write(self.style.SUCCESS("Deprecated products (code - name):"))
            for code, name in sorted(deprecated_products, key=lambda item: item[0]):
                self.stdout.write(f"- {code} - {name}")
        if manually_mapped:
            self.stdout.write(self.style.SUCCESS("Manual category mappings applied (code - name - category):"))
            for code, name, category_name in sorted(manually_mapped, key=lambda item: item[0]):
                self.stdout.write(f"- {code} - {name} - {category_name}")

    @staticmethod
    def _resolve_path(raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path
        return Path.cwd() / path

    @staticmethod
    def _require_string(row: dict[str, Any], key: str) -> str:
        value = row.get(key)
        if value is None or str(value).strip() == "":
            raise CommandError(f"Missing required field '{key}' in dataset row: {row}")
        return str(value).strip()

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise CommandError(f"Invalid decimal value: {value}") from exc

    @staticmethod
    def _to_optional_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise CommandError(f"Invalid integer value: {value}") from exc

    @staticmethod
    def _find_duplicates(values) -> set[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for value in values:
            normalized = str(value).strip()
            if not normalized:
                continue
            if normalized in seen:
                duplicates.add(normalized)
                continue
            seen.add(normalized)
        return duplicates

    @staticmethod
    def _product_changed(product: Product, defaults: dict[str, Any]) -> bool:
        for field_name, value in defaults.items():
            current = getattr(product, field_name)
            if field_name == "product_category":
                current_id = getattr(current, "id", None)
                value_id = getattr(value, "id", None)
                if current_id != value_id:
                    return True
                continue
            if current != value:
                return True
        return False
