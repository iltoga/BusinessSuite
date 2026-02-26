from unittest.mock import patch

from django.test import TestCase

from core.models.local_resilience import LocalResilienceSettings, SyncChangeLog
from core.services.local_resilience_service import LocalResilienceService


class LocalResilienceServiceTests(TestCase):
    @patch("core.services.local_resilience_service.bootstrap_snapshot")
    def test_enable_bootstrap_respects_existing_changelog_guard(self, bootstrap_snapshot_mock):
        settings_obj = LocalResilienceSettings.get_solo()
        settings_obj.enabled = False
        settings_obj.save(update_fields=["enabled", "updated_at"])

        SyncChangeLog.objects.create(
            source_node="node-a",
            model_label="products.product",
            object_pk="1",
            operation=SyncChangeLog.OP_UPSERT,
            payload={"id": 1},
        )

        LocalResilienceService.update_settings(enabled=True)

        bootstrap_snapshot_mock.assert_called_once_with(force=False)
