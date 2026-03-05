from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.models import AppSetting
from core.services.app_setting_service import AppSettingService


@receiver(post_save, sender=AppSetting)
def _invalidate_app_setting_cache_on_save(sender, instance, **kwargs):
    AppSettingService.invalidate_cache()


@receiver(post_delete, sender=AppSetting)
def _invalidate_app_setting_cache_on_delete(sender, instance, **kwargs):
    AppSettingService.invalidate_cache()
