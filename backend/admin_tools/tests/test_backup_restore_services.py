import io
import json
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from admin_tools import services
from customers.models import Customer
from invoices.models.invoice import Invoice
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

    def test_restore_handles_ambiguous_legacy_customer_natural_key(self):
        duplicate_customer_fields = {
            "created_at": "2026-02-18T00:00:00Z",
            "updated_at": "2026-02-18T00:00:00Z",
            "title": None,
            "customer_type": "person",
            "first_name": "Daegel",
            "last_name": "Reighard",
            "company_name": None,
            "email": None,
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
            "passport_file": "",
            "passport_metadata": None,
            "gender": None,
            "address_bali": None,
            "address_abroad": None,
            "notify_documents_expiration": False,
            "notify_by": None,
            "notification_sent": False,
            "active": True,
        }

        legacy_objects = [
            {
                "model": "customers.customer",
                "fields": duplicate_customer_fields,
            },
            {
                "model": "customers.customer",
                "fields": {**duplicate_customer_fields, "company_name": "PT Plumeria Paradise Estates"},
            },
            {
                "model": "invoices.invoice",
                "pk": 48,
                "fields": {
                    "customer": {
                        "full_name": "Daegel Reighard",
                        "email": None,
                        "birthdate": None,
                        "active": True,
                    },
                    "invoice_no": 20260048,
                    "invoice_date": "2026-02-18",
                    "due_date": "2026-02-25",
                    "sent": False,
                    "status": "created",
                    "notes": "",
                    "total_amount": "0.00",
                    "imported": False,
                    "imported_from_file": None,
                    "raw_extracted_data": None,
                    "mobile_phone": None,
                    "bank_details": None,
                    "created_at": "2026-02-18T00:00:00Z",
                    "updated_at": "2026-02-18T00:00:00Z",
                    "created_by": None,
                    "updated_by": None,
                },
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = _build_archive(tmpdir, legacy_objects)
            messages = list(services.restore_from_file(archive_path, include_users=False))

        self.assertTrue(any("ambiguous_refs=" in message for message in messages))
        self.assertEqual(Customer.objects.count(), 2)
        invoice = Invoice.objects.get(pk=48)
        self.assertIsNotNone(invoice.customer_id)

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
                self.deleted_paths = []

            def exists(self, path):
                return False

            def delete(self, path):
                self.deleted_paths.append(path)
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
        self.assertEqual(destination_storage.deleted_paths, [])
        self.assertEqual(Customer.objects.get(pk=1).passport_file.name, "migrated/tmpfiles/sample.txt")
        self.assertTrue(
            any("RESTORE_SUMMARY: copied=1 skipped_existing=0 missing_source=0" in message for message in messages)
        )

    def test_restore_external_storage_skips_self_copy_for_same_bucket(self):
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
                    "passport_file": "documents/passport.pdf",
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
                    "bucket": "same-bucket",
                    "endpoint_url": "https://example-r2.invalid",
                    "location": "",
                },
            },
            "files": [{"path": "documents/passport.pdf"}],
        }

        class _LazyObjectHandle:
            def __init__(self, storage, path):
                self._storage = storage
                self._path = path
                self._offset = 0

            def read(self, size=-1):
                data = self._storage.objects.get(self._path)
                if data is None:
                    raise FileNotFoundError(self._path)
                if size is None or size < 0:
                    chunk = data[self._offset :]
                    self._offset = len(data)
                    return chunk
                chunk = data[self._offset : self._offset + size]
                self._offset += len(chunk)
                return chunk

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        class _SharedS3Storage:
            __module__ = "storages.backends.s3boto3"

            def __init__(self):
                self.bucket_name = "same-bucket"
                self.endpoint_url = "https://example-r2.invalid"
                self.location = ""
                self.objects = {"documents/passport.pdf": b"passport-bytes"}
                self.deleted_paths = []
                self.saved_paths = []

            def open(self, path, mode="rb"):
                return _LazyObjectHandle(self, path)

            def exists(self, path):
                return path in self.objects

            def delete(self, path):
                self.deleted_paths.append(path)
                self.objects.pop(path, None)

            def save(self, path, file_obj):
                self.saved_paths.append(path)
                self.objects[path] = file_obj.read()
                return path

        shared_storage = _SharedS3Storage()

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = _build_archive(tmpdir, fixture_objects, manifest=manifest)
            with patch("admin_tools.services.default_storage", shared_storage):
                messages = list(services.restore_from_file(archive_path, include_users=False))

        self.assertTrue(any("skipping media copy" in message for message in messages))
        self.assertEqual(shared_storage.deleted_paths, [])
        self.assertEqual(shared_storage.saved_paths, [])
        self.assertIn("documents/passport.pdf", shared_storage.objects)
        self.assertEqual(Customer.objects.get(pk=1).passport_file.name, "documents/passport.pdf")
        self.assertTrue(
            any("RESTORE_SUMMARY: copied=0 skipped_existing=1 missing_source=0" in message for message in messages)
        )

    def test_restore_external_storage_skips_existing_target_files_without_delete(self):
        fixture_objects = [
            {
                "model": "customers.customer",
                "pk": 1,
                "fields": {
                    "created_at": "2026-02-18T00:00:00Z",
                    "updated_at": "2026-02-18T00:00:00Z",
                    "title": None,
                    "customer_type": "person",
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "company_name": None,
                    "email": "jane@example.com",
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
                return io.BytesIO(b"source-content")

        class _FakeDestinationStorage:
            def __init__(self):
                self.deleted_paths = []
                self.saved_paths = []
                self.existing_paths = {"tmpfiles/sample.txt"}

            def exists(self, path):
                return path in self.existing_paths

            def delete(self, path):
                self.deleted_paths.append(path)
                self.existing_paths.discard(path)

            def save(self, path, file_obj):
                self.saved_paths.append(path)
                self.existing_paths.add(path)
                return path

        destination_storage = _FakeDestinationStorage()

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = _build_archive(tmpdir, fixture_objects, manifest=manifest)
            with patch("admin_tools.services.default_storage", destination_storage), patch(
                "admin_tools.services._build_source_storage_from_manifest",
                return_value=(_FakeSourceStorage(), None),
            ):
                messages = list(services.restore_from_file(archive_path, include_users=False))

        self.assertEqual(destination_storage.deleted_paths, [])
        self.assertEqual(destination_storage.saved_paths, [])
        self.assertEqual(Customer.objects.get(pk=1).passport_file.name, "tmpfiles/sample.txt")
        self.assertTrue(
            any("RESTORE_SUMMARY: copied=0 skipped_existing=1 missing_source=0" in message for message in messages)
        )

    def test_restore_external_storage_summary_counts_missing_source(self):
        fixture_objects = [
            {
                "model": "customers.customer",
                "pk": 1,
                "fields": {
                    "created_at": "2026-02-18T00:00:00Z",
                    "updated_at": "2026-02-18T00:00:00Z",
                    "title": None,
                    "customer_type": "person",
                    "first_name": "Missing",
                    "last_name": "Source",
                    "company_name": None,
                    "email": "missing@example.com",
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
                    "passport_file": "tmpfiles/missing.txt",
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
            "files": [{"path": "tmpfiles/missing.txt"}],
        }

        class _MissingSourceStorage:
            def open(self, path, mode="rb"):
                raise FileNotFoundError(path)

        class _DestinationStorage:
            def exists(self, path):
                return False

            def save(self, path, file_obj):
                return path

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = _build_archive(tmpdir, fixture_objects, manifest=manifest)
            with patch("admin_tools.services.default_storage", _DestinationStorage()), patch(
                "admin_tools.services._build_source_storage_from_manifest",
                return_value=(_MissingSourceStorage(), None),
            ):
                messages = list(services.restore_from_file(archive_path, include_users=False))

        self.assertTrue(any("RESTORE_SUMMARY: copied=0 skipped_existing=0 missing_source=1" in m for m in messages))
