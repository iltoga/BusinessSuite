import io
import json
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from admin_tools import services
from customers.models import Customer
from products.models.product import Product
from products.models.task import Task


def _build_archive(base_dir: str, objects: list[dict], manifest: dict | None = None) -> str:
    root = Path(base_dir)
    data_path = root / "data.json"
    data_path.write_text(json.dumps(objects), encoding="utf-8")

    manifest_path = None
    if manifest is not None:
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    archive_path = root / "backup.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(data_path, arcname="data.json")
        if manifest_path:
            tar.add(manifest_path, arcname="manifest.json")

    return str(archive_path)


class BackupSerializationTests(SimpleTestCase):
    def test_backup_uses_pk_based_dumpdata(self):
        class _StopBackup(Exception):
            pass

        def _stop_after_args(*args, **kwargs):
            raise _StopBackup(args)

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(services, "BACKUPS_DIR", tmpdir), patch(
            "admin_tools.services.call_command", side_effect=_stop_after_args
        ):
            gen = services.backup_all(include_users=False)
            self.assertEqual(next(gen), "Starting Django dumpdata backup...")
            with self.assertRaises(_StopBackup) as raised:
                next(gen)

        dump_args = raised.exception.args[0]
        self.assertEqual(dump_args[0], "dumpdata")
        self.assertNotIn("--natural-foreign", dump_args)
        self.assertNotIn("--natural-primary", dump_args)


class RestoreCompatibilityTests(TestCase):
    def test_restore_handles_legacy_dict_fk_fixture(self):
        legacy_objects = [
            {
                "model": "products.product",
                "fields": {
                    "name": "Work Permit",
                    "code": "WORK_PERMIT",
                    "description": "",
                    "immigration_id": None,
                    "base_price": "2000000.00",
                    "product_type": "visa",
                    "validity": None,
                    "required_documents": "",
                    "optional_documents": "",
                    "documents_min_validity": None,
                    "created_at": "2026-02-18T00:00:00Z",
                    "updated_at": "2026-02-18T00:00:00Z",
                    "created_by": None,
                    "updated_by": None,
                },
            },
            {
                "model": "products.task",
                "pk": 1,
                "fields": {
                    "product": {
                        "code": "WORK_PERMIT",
                        "name": "Work Permit",
                        "base_price": "2000000.00",
                        "product_type": "visa",
                    },
                    "step": 1,
                    "last_step": False,
                    "name": "Document Collection",
                    "description": "",
                    "cost": "0.00",
                    "duration": 3,
                    "duration_is_business_days": False,
                    "notify_days_before": 0,
                    "add_task_to_calendar": False,
                    "notify_customer": False,
                },
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = _build_archive(tmpdir, legacy_objects)
            messages = list(services.restore_from_file(archive_path, include_users=False))

        self.assertTrue(any("Normalized legacy fixture references" in message for message in messages))
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(Task.objects.count(), 1)

        task = Task.objects.select_related("product").get(pk=1)
        self.assertEqual(task.product.code, "WORK_PERMIT")

    def test_restore_external_storage_copies_files_and_rewires_filefields(self):
        fixture_objects = [
            {
                "model": "customers.customer",
                "pk": 1,
                "fields": {
                    "created_at": "2026-02-18T00:00:00Z",
                    "updated_at": "2026-02-18T00:00:00Z",
                    "title": None,
                    "customer_type": "person",
                    "first_name": "John",
                    "last_name": "Doe",
                    "company_name": None,
                    "email": "john@example.com",
                    "telephone": None,
                    "whatsapp": None,
                    "telegram": None,
                    "facebook": None,
                    "instagram": None,
                    "twitter": None,
                    "npwp": None,
                    "nationality": None,
                    "birthdate": None,
                    "birth_place": None,
                    "passport_number": None,
                    "passport_issue_date": None,
                    "passport_expiration_date": None,
                    "passport_file": "tmpfiles/sample.txt",
                    "passport_metadata": None,
                    "gender": None,
                    "address_bali": None,
                    "address_abroad": None,
                    "notify_documents_expiration": False,
                    "notify_by": None,
                    "notification_sent": False,
                    "active": True,
                },
            }
        ]
        manifest = {
            "media": {
                "included_in_archive": False,
                "mode": "external_storage_reference",
                "storage": {
                    "backend": "storages.backends.s3boto3.S3Boto3Storage",
                    "provider": "s3",
                    "bucket": "origin-bucket",
                },
            },
            "files": [{"path": "tmpfiles/sample.txt"}],
        }

        class _FakeSourceStorage:
            def open(self, path, mode="rb"):
                return io.BytesIO(b"test-content")

        class _FakeDestinationStorage:
            def __init__(self):
                self.saved_paths = []

            def exists(self, path):
                return False

            def delete(self, path):
                return None

            def save(self, path, file_obj):
                self.saved_paths.append(path)
                return f"migrated/{path}"

        destination_storage = _FakeDestinationStorage()

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = _build_archive(tmpdir, fixture_objects, manifest=manifest)
            with patch("admin_tools.services.default_storage", destination_storage), patch(
                "admin_tools.services._build_source_storage_from_manifest",
                return_value=(_FakeSourceStorage(), None),
            ):
                messages = list(services.restore_from_file(archive_path, include_users=False))

        self.assertTrue(any("source object storage" in message for message in messages))
        self.assertEqual(destination_storage.saved_paths, ["tmpfiles/sample.txt"])
        self.assertEqual(Customer.objects.get(pk=1).passport_file.name, "migrated/tmpfiles/sample.txt")
