from unittest.mock import patch

from django.db.models.fields.files import FileField
from django.test import SimpleTestCase, override_settings

from admin_tools import services


class _FakeStorage:
    def __init__(self, *, existing_keys: set[str], location: str = "media"):
        self._existing_keys = set(existing_keys)
        self.location = location

    def exists(self, key: str) -> bool:
        return key in self._existing_keys

    def url(self, key: str) -> str:
        return f"https://bucket.test/{key}"

    def path(self, key: str) -> str:
        raise NotImplementedError("Object storage has no local filesystem path.")


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

        with patch.object(services, "default_storage", fake_storage), patch.object(services.apps, "get_models") as models:
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

        with patch.object(services, "default_storage", fake_storage), patch.object(services.apps, "get_models") as models:
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

        with patch.object(services, "default_storage", fake_storage), patch.object(services.apps, "get_models") as models:
            models.return_value = [fake_model]
            repairs = services.repair_media_paths()

        self.assertEqual(len(repairs), 1)
        self.assertIn("refreshed file_link", repairs[0])
        current_file_value = getattr(obj, field_name)
        self.assertEqual(getattr(current_file_value, "name", current_file_value), db_path)
        self.assertEqual(obj.file_link, f"https://bucket.test/{db_path}")
        self.assertEqual(obj.saved_update_fields, ["file_link"])
