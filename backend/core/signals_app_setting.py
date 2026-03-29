"""
FILE_ROLE: Signal handlers for app setting persistence and side effects.

KEY_COMPONENTS:
- _invalidate_app_setting_cache_on_save: Module symbol.
- _invalidate_app_setting_cache_on_delete: Module symbol.

INTERACTIONS:
- Depends on: core.models, core.services, Django signal machinery, or middleware hooks as appropriate.

AI_GUIDELINES:
- Keep this module focused on framework integration and small hook functions.
- Do not move domain orchestration here when a service already owns the workflow.
"""

from __future__ import annotations

from core.models import AppSetting
from core.services.app_setting_service import AppSettingService
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


@receiver(post_save, sender=AppSetting)
def _invalidate_app_setting_cache_on_save(sender, instance, **kwargs):
    AppSettingService.invalidate_cache()


@receiver(post_delete, sender=AppSetting)
def _invalidate_app_setting_cache_on_delete(sender, instance, **kwargs):
    AppSettingService.invalidate_cache()
