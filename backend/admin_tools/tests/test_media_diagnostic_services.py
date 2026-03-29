"""
FILE_ROLE: Test coverage for the admin tools app.

KEY_COMPONENTS:
- _FakeStorage: Private helper.
- _FakeFileValue: Private helper.
- _FakeModelObject: Private helper.
- _FakeManager: Private helper.
- _FakeMeta: Private helper.
- _FakeFileField: Private helper.
- _FakeJSONField: Private helper.
- _build_fake_model: Private helper.

INTERACTIONS:
- Depends on: Django settings/bootstrap and adjacent app services or middleware in this module.

AI_GUIDELINES:
- Keep the file focused on its narrow responsibility and avoid mixing in unrelated business logic.
- Preserve existing runtime contracts for app routing, model behavior, and service boundaries.
"""

from unittest.mock import patch

from admin_tools import services
from django.db.models import JSONField
from django.db.models.fields.files import FileField
from django.test import SimpleTestCase, override_settings


class _FakeStorage:
    def __init__(self, *, existing_keys: set[str], location: str = "media"):
        self._existing_keys = set(existing_keys)
        self.location = location
        self.deleted_keys: list[str] = []

    def exists(self, key: str) -> bool:
        return key in self._existing_keys

    def url(self, key: str) -> str:
        return f"https://bucket.test/{key}"

    def path(self, key: str) -> str:
        raise NotImplementedError("Object storage has no local filesystem path.")

    def delete(self, key: str) -> None:
        self.deleted_keys.append(key)
        self._existing_keys.discard(key)

    def size(self, key: str) -> int:
        return len(key.encode("utf-8"))


class _FakeFileValue:
    def __init__(self, name: str):
        self.name = name

    def __bool__(self) -> bool:
        return bool(self.name)


class _FakeModelObject:
    def __init__(self, *, pk: int, field_name: str, file_name: str, file_link: str = "", upload_folder: str = ""):
        self.pk = pk
        setattr(self, field_name, _FakeFileValue(file_name))
        self.file_link = file_link
        self.upload_folder = upload_folder
        self.saved_update_fields: list[str] = []

    def save(self, update_fields=None):
        self.saved_update_fields = list(update_fields or [])


class _FakeManager:
    def __init__(self, objects, *, field_name: str):
        self._objects = list(objects)
        self._field_name = field_name

    def all(self):
        return list(self._objects)

    def exclude(self, **kwargs):
        expected_empty = kwargs.get(self._field_name, None)
        items = []
        for obj in self._objects:
            value = getattr(obj, self._field_name, None)
            current_name = getattr(value, "name", str(value or ""))
            if current_name != expected_empty:
                items.append(obj)
        return items


class _FakeMeta:
    def __init__(self, *, label: str, fields):
        self.label = label
        self._fields = list(fields)

    def get_fields(self):
        return list(self._fields)


class _FakeFileField(FileField):
    def __init__(self, *, name: str):
        super().__init__(upload_to="")
        self.name = name

    def generate_filename(self, instance, filename):
        return filename


class _FakeJSONField(JSONField):
    def __init__(self, *, name: str):
        super().__init__()
        self.name = name


def _build_fake_model(*, label: str, field_name: str, objects):
    field = _FakeFileField(name=field_name)

    return type(
        "_FakeModel",
        (),
        {
            "_meta": _FakeMeta(label=label, fields=[field]),
            "objects": _FakeManager(objects, field_name=field_name),
        },
    )


def _build_fake_multi_field_model(*, label: str, fields, objects):
    return type(
        "_FakeMultiFieldModel",
        (),
        {
            "_meta": _FakeMeta(label=label, fields=fields),
            "_default_manager": _FakeManager(objects, field_name=getattr(fields[0], "name", "file")),
        },
    )


class _FakeMediaStoreAdapter:
    def __init__(self, *, files_by_prefix: dict[str, list[str]]):
        self.files_by_prefix = {key: list(value) for key, value in files_by_prefix.items()}
        self.deleted: list[str] = []

    def iter_files(self, prefix: str):
        return list(self.files_by_prefix.get(prefix, []))

    def delete(self, key: str):
        self.deleted.append(key)

    def size(self, key: str) -> int:
        return len(key)


@override_settings(
    MEDIA_URL="/uploads/",
    MEDIA_ROOT="/srv/app/files/media/",
    DOCUMENTS_FOLDER="documents",
)
class MediaDiagnosticServiceTests(SimpleTestCase):
    def test_check_media_files_resolves_prefixed_storage_key(self):
        field_name = "file"
        db_path = "documents/Alice_1/application_9/passport.pdf"
        storage_path = f"media/{db_path}"
        obj = _FakeModelObject(
            pk=101,
            field_name=field_name,
            file_name=db_path,
            file_link=f"https://bucket.test/{db_path}",
            upload_folder="documents/Alice_1/application_9",
        )
        fake_model = _build_fake_model(label="customer_applications.Document", field_name=field_name, objects=[obj])
        fake_storage = _FakeStorage(existing_keys={storage_path}, location="media")

        with patch.object(services, "default_storage", fake_storage), patch.object(
            services.apps, "get_models"
        ) as models:
            models.return_value = [fake_model]
            results = services.check_media_files()

        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertTrue(row["exists"])
        self.assertEqual(row["path"], db_path)
        self.assertEqual(row["resolved_path"], storage_path)
        self.assertEqual(row["url"], f"https://bucket.test/{storage_path}")
        self.assertTrue(row["discrepancy"])

    def test_repair_media_paths_relinks_db_path_for_prefixed_object(self):
        field_name = "file"
        db_path = "documents/Alice_1/application_9/passport.pdf"
        storage_path = f"media/{db_path}"
        obj = _FakeModelObject(
            pk=202,
            field_name=field_name,
            file_name=db_path,
            file_link=f"https://bucket.test/{db_path}",
            upload_folder="documents/Alice_1/application_9",
        )
        fake_model = _build_fake_model(label="customer_applications.Document", field_name=field_name, objects=[obj])
        fake_storage = _FakeStorage(existing_keys={storage_path}, location="media")

        with patch.object(services, "default_storage", fake_storage), patch.object(
            services.apps, "get_models"
        ) as models:
            models.return_value = [fake_model]
            repairs = services.repair_media_paths()

        self.assertEqual(len(repairs), 1)
        self.assertIn("relinked", repairs[0])
        self.assertEqual(getattr(obj, field_name), storage_path)
        self.assertEqual(obj.file_link, f"https://bucket.test/{storage_path}")
        self.assertCountEqual(obj.saved_update_fields, [field_name, "file_link"])

    def test_repair_media_paths_refreshes_file_link_when_path_exists(self):
        field_name = "passport_file"
        db_path = "documents/Bob_3/passport.png"
        obj = _FakeModelObject(
            pk=303,
            field_name=field_name,
            file_name=db_path,
            file_link="https://bucket.test/stale/path.png",
            upload_folder="documents/Bob_3",
        )
        fake_model = _build_fake_model(label="customers.Customer", field_name=field_name, objects=[obj])
        fake_storage = _FakeStorage(existing_keys={db_path}, location="media")

        with patch.object(services, "default_storage", fake_storage), patch.object(
            services.apps, "get_models"
        ) as models:
            models.return_value = [fake_model]
            repairs = services.repair_media_paths()

        self.assertEqual(len(repairs), 1)
        self.assertIn("refreshed file_link", repairs[0])
        current_file_value = getattr(obj, field_name)
        self.assertEqual(getattr(current_file_value, "name", current_file_value), db_path)
        self.assertEqual(obj.file_link, f"https://bucket.test/{db_path}")
        self.assertEqual(obj.saved_update_fields, ["file_link"])

    def test_cleanup_unlinked_media_files_dry_run_keeps_referenced_paths(self):
        adapter = _FakeMediaStoreAdapter(
            files_by_prefix={
                "documents": [
                    "documents/linked.pdf",
                    "documents/orphan.pdf",
                ],
                "ocr_previews": ["ocr_previews/job-1.png"],
                "tmp": [],
                "tmpfiles": [],
            }
        )

        file_field = _FakeFileField(name="file")
        json_field = _FakeJSONField(name="result")
        obj = type(
            "_OwnedFileObject",
            (),
            {
                "file": _FakeFileValue("documents/linked.pdf"),
                "result": {"preview_storage_path": "ocr_previews/job-1.png"},
            },
        )()
        fake_model = _build_fake_multi_field_model(
            label="core.CleanupOwner",
            fields=[file_field, json_field],
            objects=[obj],
        )

        with (
            patch.object(services, "get_media_store_adapter", return_value=adapter),
            patch.object(services.apps, "get_models", return_value=[fake_model]),
        ):
            result = services.cleanup_unlinked_media_files(dry_run=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["orphanedFiles"], 1)
        self.assertEqual(result["deletedFiles"], 0)
        self.assertEqual(result["files"], [{"path": "documents/orphan.pdf", "sizeBytes": 20}])
        self.assertEqual(adapter.deleted, [])

    def test_cleanup_unlinked_media_files_deletes_orphans_when_not_dry_run(self):
        adapter = _FakeMediaStoreAdapter(
            files_by_prefix={
                "documents": ["documents/orphan.pdf"],
                "ocr_previews": [],
                "tmp": ["tmp/unreferenced.txt"],
                "tmpfiles": [],
            }
        )

        fake_model = _build_fake_multi_field_model(
            label="core.EmptyOwner",
            fields=[_FakeJSONField(name="result")],
            objects=[type("_EmptyObject", (), {"result": {}})()],
        )

        with (
            patch.object(services, "get_media_store_adapter", return_value=adapter),
            patch.object(services.apps, "get_models", return_value=[fake_model]),
        ):
            result = services.cleanup_unlinked_media_files(dry_run=False)

        self.assertTrue(result["ok"])
        self.assertFalse(result["dryRun"])
        self.assertEqual(result["orphanedFiles"], 2)
        self.assertEqual(result["deletedFiles"], 2)
        self.assertCountEqual(adapter.deleted, ["documents/orphan.pdf", "tmp/unreferenced.txt"])

    def test_cleanup_unlinked_media_files_emits_progress_updates(self):
        adapter = _FakeMediaStoreAdapter(
            files_by_prefix={
                "documents": ["documents/orphan.pdf"],
                "ocr_previews": [],
                "tmp": [],
                "tmpfiles": [],
            }
        )

        fake_model = _build_fake_multi_field_model(
            label="core.EmptyOwner",
            fields=[_FakeJSONField(name="result")],
            objects=[type("_EmptyObject", (), {"result": {}})()],
        )
        progress_updates: list[dict] = []

        with (
            patch.object(services, "get_media_store_adapter", return_value=adapter),
            patch.object(services.apps, "get_models", return_value=[fake_model]),
        ):
            services.cleanup_unlinked_media_files(dry_run=True, progress_callback=progress_updates.append)

        event_names = [update.get("event") for update in progress_updates]
        self.assertIn("media_cleanup_started", event_names)
        self.assertIn("media_cleanup_found", event_names)
        self.assertIn("media_cleanup_finished", event_names)
        found_update = next(update for update in progress_updates if update.get("event") == "media_cleanup_found")
        self.assertEqual(found_update.get("file"), {"path": "documents/orphan.pdf", "sizeBytes": 20})
