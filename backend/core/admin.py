from django.contrib import admin

from .models.ai_request_usage import AIRequestUsage
from .models.app_setting import AppSetting
from .models.calendar_reminder import CalendarReminder
from .models.country_code import CountryCode
from .models.holiday import Holiday
from .models.ui_settings import UiSettings
from .models.user_settings import UserSettings
from .models.rbac_rule import RbacMenuRule, RbacFieldRule

admin.site.register(Holiday)
admin.site.register(CountryCode)
admin.site.register(UserSettings)
admin.site.register(CalendarReminder)
admin.site.register(UiSettings)


@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    list_display = ("name", "scope", "value", "updated_at", "updated_by")
    list_filter = ("scope", "updated_at")
    search_fields = ("name", "value", "description")

    def save_model(self, request, obj, form, change):
        if request.user and request.user.is_authenticated:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(RbacMenuRule)
class RbacMenuRuleAdmin(admin.ModelAdmin):
    list_display = ("menu_id", "group", "role", "is_visible")
    list_filter = ("group", "role", "is_visible")
    search_fields = ("menu_id",)


@admin.register(RbacFieldRule)
class RbacFieldRuleAdmin(admin.ModelAdmin):
    list_display = ("model_name", "field_name", "group", "role", "can_read", "can_write")
    list_filter = ("group", "role", "can_read", "can_write", "model_name")
    search_fields = ("model_name", "field_name")


@admin.register(AIRequestUsage)
class AIRequestUsageAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "feature",
        "provider",
        "model",
        "success",
        "total_tokens",
        "cost_usd",
        "latency_ms",
    )
    list_filter = ("feature", "provider", "success", "created_at")
    search_fields = ("feature", "model", "request_id")
