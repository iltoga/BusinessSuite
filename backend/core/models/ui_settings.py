"""
FILE_ROLE: Primary data models for the core app.

KEY_COMPONENTS:
- UiSettings: Module symbol.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on model definitions and local invariants.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class UiSettings(models.Model):
    singleton_key = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    use_overlay_menu = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_ui_settings",
    )

    class Meta:
        verbose_name = "UI Settings"
        verbose_name_plural = "UI Settings"

    def __str__(self) -> str:
        return f"UI settings (overlay menu {'enabled' if self.use_overlay_menu else 'disabled'})"

    @classmethod
    def get_solo(cls) -> "UiSettings":
        settings_obj, _ = cls.objects.get_or_create(singleton_key=1)
        return settings_obj
