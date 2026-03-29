"""
FILE_ROLE: Service-layer logic for the core app.

KEY_COMPONENTS:
- LocalResilienceService: Service class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on its narrow layer boundary and avoid moving cross-cutting workflow code here.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

from __future__ import annotations

from core.models.local_resilience import LocalResilienceSettings, MediaManifestEntry, SyncCursor
from core.services.sync_service import bootstrap_snapshot


class LocalResilienceService:
    @staticmethod
    def get_settings() -> LocalResilienceSettings:
        return LocalResilienceSettings.get_solo()

    @staticmethod
    def update_settings(
        *, enabled: bool | None = None, desktop_mode: str | None = None, updated_by=None
    ) -> LocalResilienceSettings:
        settings_obj = LocalResilienceSettings.get_solo()
        was_enabled = bool(settings_obj.enabled)
        if enabled is not None:
            settings_obj.enabled = bool(enabled)
        if desktop_mode in {
            LocalResilienceSettings.MODE_LOCAL_PRIMARY,
            LocalResilienceSettings.MODE_REMOTE_PRIMARY,
        }:
            settings_obj.desktop_mode = desktop_mode
        settings_obj.updated_by = updated_by
        settings_obj.save()

        if settings_obj.enabled and not was_enabled:
            # Build initial changelog snapshot for first-time replica bootstrap.
            bootstrap_snapshot(force=False)

        return settings_obj

    @staticmethod
    def reset_vault_epoch(*, updated_by=None) -> LocalResilienceSettings:
        settings_obj = LocalResilienceSettings.get_solo()
        settings_obj.vault_epoch = int(settings_obj.vault_epoch) + 1
        settings_obj.updated_by = updated_by
        settings_obj.save(update_fields=["vault_epoch", "updated_by", "updated_at"])
        SyncCursor.objects.all().update(
            last_pulled_seq=0,
            last_pushed_seq=0,
            last_pulled_at=None,
            last_pushed_at=None,
            last_error="",
        )
        MediaManifestEntry.objects.all().delete()
        return settings_obj
