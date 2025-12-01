import json
import os
import tarfile
import tempfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from admin_tools import services
from customers.models import Customer


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="test_media_"))
class AdminToolsBackupRestoreTest(TransactionTestCase):
    def setUp(self):
        # Monkeypatch BACKUPS_DIR to a temporary directory for tests
        self._orig_backups_dir = services.BACKUPS_DIR
        self.backups_dir = tempfile.mkdtemp(prefix="test_backups_")
        services.BACKUPS_DIR = self.backups_dir

    def tearDown(self):
        # Restore module constant
        services.BACKUPS_DIR = self._orig_backups_dir

    def _write_media_file(self, rel_path, content=b"hello world"):
        default_storage.save(rel_path, ContentFile(content))
        return rel_path

    def test_backup_includes_media_and_data(self):
        # Create a customer with a passport file
        rel_path = "documents/test_customer/passport.jpg"
        content = b"fake-passport-image"
        self._write_media_file(rel_path, content)
        customer = Customer.objects.create(first_name="Test", last_name="User")
        customer.passport_file = rel_path
        customer.passport_number = "P123456"
        customer.save()

        # Run backup
        backup_path = services.backup_all(progress_callback=lambda m: None, include_users=False)
        self.assertTrue(os.path.exists(backup_path))

        # Inspect tar contents
        with tarfile.open(backup_path, "r:gz") as tar:
            members = [m.name for m in tar.getmembers()]
            self.assertIn("data.json", members)
            self.assertIn("manifest.json", members)
            self.assertIn(os.path.join("media", rel_path), members)

            # Check manifest lists the file
            member = tar.getmember("manifest.json")
            f = tar.extractfile(member)
            manifest = json.load(f)
            self.assertGreater(manifest.get("included_files_count", 0), 0)
            paths = [p["path"] for p in manifest.get("files", [])]
            self.assertIn(rel_path, paths)

    def test_restore_restores_media_and_data(self):
        # Create data and media
        rel_path = "documents/restore_customer/passport.jpg"
        content = b"passport-data"
        self._write_media_file(rel_path, content)
        customer = Customer.objects.create(first_name="Restore", last_name="User")
        customer.passport_file = rel_path
        customer.passport_number = "P1234567"
        customer.save()

        # Run backup
        backup_path = services.backup_all(progress_callback=lambda m: None, include_users=False)
        self.assertTrue(os.path.exists(backup_path))

        # Delete media and DB to simulate a loss
        default_storage.delete(rel_path)
        Customer.objects.all().delete()

        # Ensure file is removed and DB is empty
        self.assertFalse(default_storage.exists(rel_path))
        self.assertEqual(Customer.objects.count(), 0)

        # Run restore
        services.restore_from_file(backup_path, progress_callback=lambda m: None, include_users=False)

        # Check that the file was restored
        self.assertTrue(default_storage.exists(rel_path))

        # Check DB record restored
        restored = Customer.objects.filter(passport_number="P1234567").first()
        self.assertIsNotNone(restored)
        self.assertEqual(restored.passport_number, "P1234567")

    def test_backup_page_shows_indicators(self):
        # Create a superuser to view the backup page
        User = get_user_model()
        superuser = User.objects.create_superuser(username="admin", email="admin@example.com", password="admin")
        self.client.force_login(superuser)

        # Create a backup with a file
        rel_path = "documents/ui_customer/passport.jpg"
        self._write_media_file(rel_path, b"ui-data")
        customer = Customer.objects.create(first_name="UI", last_name="User")
        customer.passport_file = rel_path
        customer.passport_number = "UI123"
        customer.save()
        # Force a 'full' backup by setting include_users=True
        backup_path = services.backup_all(progress_callback=lambda m: None, include_users=True)
        # Backup created in services.BACKUPS_DIR (same folder used by view)

        url = reverse("admin_tools:backup_page")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("Full", content)
        self.assertIn("Files:", content)

    def test_delete_all_backups_endpoint(self):
        # Create a backup file in the backups dir used by the view
        rel_path = "documents/delete_customer/passport.jpg"
        self._write_media_file(rel_path, b"delete-test")
        customer = Customer.objects.create(first_name="Delete", last_name="User")
        customer.passport_file = rel_path
        customer.passport_number = "DEL123"
        customer.save()

        backup_path = services.backup_all(progress_callback=lambda m: None, include_users=False)
        # Backup created in services.BACKUPS_DIR (same folder used by view)

        # Login as superuser and call delete endpoint
        from django.contrib.auth import get_user_model

        User = get_user_model()
        superuser = User.objects.create_superuser(username="admin2", email="a@example.com", password="admin2")
        self.client.force_login(superuser)

        url = reverse("admin_tools:delete_backups")
        resp = self.client.post(url, {}, HTTP_X_CSRFTOKEN="dummy")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertGreaterEqual(data.get("deleted", 0), 1)

        # Ensure directory is empty
        backups_dir = services.BACKUPS_DIR
        backups_list = os.listdir(backups_dir)
        self.assertEqual(len(backups_list), 0)

    def test_restore_page_shows_backups_dropdown(self):
        # Ensure the restore page dropdown shows backups created in the backups_dir
        rel_path = "documents/restore_ui/passport.jpg"
        self._write_media_file(rel_path, b"restore-ui")
        customer = Customer.objects.create(first_name="RestoreUI", last_name="User")
        customer.passport_file = rel_path
        customer.passport_number = "UI777"
        customer.save()

        backup_path = services.backup_all(progress_callback=lambda m: None, include_users=False)
        # Backup created in services.BACKUPS_DIR (same folder used by view)

        # Login as superuser and fetch restore page
        from django.contrib.auth import get_user_model

        User = get_user_model()
        superuser = User.objects.create_superuser(username="admin3", email="a3@example.com", password="admin3")
        self.client.force_login(superuser)

        url = reverse("admin_tools:restore_page")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn(os.path.basename(backup_path), content)

    def test_backups_json_endpoint(self):
        rel_path = "documents/json_ui/passport.jpg"
        self._write_media_file(rel_path, b"json-ui")
        customer = Customer.objects.create(first_name="JsonUI", last_name="User")
        customer.passport_file = rel_path
        customer.passport_number = "JSON1"
        customer.save()
        backup_path = services.backup_all(progress_callback=lambda m: None, include_users=False)

        from django.contrib.auth import get_user_model

        User = get_user_model()
        superuser = User.objects.create_superuser(username="adminjson", email="aj@example.com", password="adminjson")
        self.client.force_login(superuser)

        url = reverse("admin_tools:backups_json")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        backups = data.get("backups", [])
        names = [b.get("filename") for b in backups]
        self.assertIn(os.path.basename(backup_path), names)
