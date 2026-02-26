from django.test import override_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from core.models.holiday import Holiday
from core.models.local_resilience import LocalResilienceSettings, SyncChangeLog, SyncConflict
from rest_framework.test import APIClient


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "sync-api-tests",
        }
    }
)
class SyncApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="sync-admin",
            email="sync-admin@example.com",
            password="password",
        )
        admin_group, _ = Group.objects.get_or_create(name="admin")
        self.user.groups.add(admin_group)
        self.client.force_authenticate(user=self.user)

    def test_pull_changes_endpoint_returns_rows(self):
        SyncChangeLog.objects.create(
            source_node="local-node",
            model_label="core.holiday",
            object_pk="1",
            operation=SyncChangeLog.OP_UPSERT,
            payload={"id": 1, "name": "Nyepi"},
            applied=True,
        )

        response = self.client.get("/api/sync/changes/pull/?after_seq=0&limit=10")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["changes"][0]["modelLabel"], "core.holiday")

    def test_push_changes_endpoint_applies_upsert(self):
        response = self.client.post(
            "/api/sync/changes/push/",
            {
                "source_node": "remote-node",
                "changes": [
                    {
                        "model_label": "core.holiday",
                        "object_pk": "99",
                        "operation": "upsert",
                        "payload": {
                            "id": 99,
                            "name": "Imported Holiday",
                            "date": "2026-01-01",
                            "country": "Indonesia",
                            "updated_at": "2026-02-25T10:00:00+00:00",
                        },
                        "source_timestamp": "2026-02-25T10:00:00+00:00",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Holiday.objects.filter(id=99, name="Imported Holiday").exists())

    def test_sync_state_endpoint_returns_latest_seq(self):
        SyncChangeLog.objects.create(
            source_node="local-node",
            model_label="core.holiday",
            object_pk="1",
            operation=SyncChangeLog.OP_UPSERT,
            payload={"id": 1, "name": "Nyepi"},
            applied=True,
        )

        response = self.client.get("/api/sync/state/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("lastSeq", payload)
        self.assertGreaterEqual(payload["lastSeq"], 1)

    def test_media_manifest_endpoint_returns_payload(self):
        response = self.client.get("/api/sync/media/manifest/?limit=5")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("items", payload)

    def test_push_older_change_creates_conflict_and_keeps_existing(self):
        settings_obj = LocalResilienceSettings.get_solo()
        settings_obj.enabled = False
        settings_obj.save(update_fields=["enabled", "updated_at"])

        response = self.client.post(
            "/api/sync/changes/push/",
            {
                "source_node": "remote-node",
                "changes": [
                    {
                        "model_label": "core.localresiliencesettings",
                        "object_pk": "1",
                        "operation": "upsert",
                        "payload": {
                            "singleton_key": 1,
                            "enabled": True,
                            "updated_at": "2000-01-01T00:00:00+00:00",
                        },
                        "source_timestamp": "2000-01-01T00:00:00+00:00",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        settings_obj.refresh_from_db()
        self.assertFalse(settings_obj.enabled)
        self.assertEqual(SyncConflict.objects.count(), 1)

    def test_session_authenticated_request_requires_explicit_token(self):
        session_client = APIClient(enforce_csrf_checks=True)
        self.assertTrue(session_client.login(username="sync-admin", password="password"))

        response = session_client.post("/api/sync/changes/push/", {"source_node": "remote-node", "changes": []}, format="json")
        self.assertEqual(response.status_code, 401)

    @override_settings(LOCAL_SYNC_REMOTE_TOKEN="sync-shared-token")
    def test_service_token_can_access_sync_api_without_user_auth(self):
        service_client = APIClient()
        service_client.credentials(HTTP_AUTHORIZATION="Bearer sync-shared-token")

        response = service_client.get("/api/sync/state/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("nodeId", payload)
