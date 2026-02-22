from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.permissions import SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR

User = get_user_model()


class AdminToolsPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_group = Group.objects.create(name="admin")
        self.admin_group_user = User.objects.create_user("backup-admin", "backup-admin@example.com", "pass")
        self.admin_group_user.groups.add(self.admin_group)
        self.regular_user = User.objects.create_user("backup-user", "backup-user@example.com", "pass")

    @patch("api.views_admin.services.backup_all", return_value=iter(["RESULT_PATH:/tmp/test-backup.tar.zst"]))
    def test_backup_start_sse_allows_admin_group_user(self, backup_all_mock):
        token = Token.objects.create(user=self.admin_group_user)

        response = self.client.get("/api/backups/start/", HTTP_AUTHORIZATION=f"Token {token.key}")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get("Content-Type", "").startswith("text/event-stream"))

    def test_backup_start_sse_rejects_non_admin_user(self):
        token = Token.objects.create(user=self.regular_user)

        response = self.client.get("/api/backups/start/", HTTP_AUTHORIZATION=f"Token {token.key}")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR)
