"""
FILE_ROLE: Service-layer logic for the core app.

KEY_COMPONENTS:
- UiSettingsService: Service class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on its narrow layer boundary and avoid moving cross-cutting workflow code here.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

from __future__ import annotations

from core.models.ui_settings import UiSettings


class UiSettingsService:
    @staticmethod
    def get_settings() -> UiSettings:
        return UiSettings.get_solo()

    @staticmethod
    def update_settings(*, use_overlay_menu: bool | None = None, updated_by=None) -> UiSettings:
        settings_obj = UiSettings.get_solo()
        if use_overlay_menu is not None:
            settings_obj.use_overlay_menu = bool(use_overlay_menu)
        settings_obj.updated_by = updated_by
        settings_obj.save()
        return settings_obj
