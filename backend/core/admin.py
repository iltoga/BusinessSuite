from django.contrib import admin

from .models.ai_request_usage import AIRequestUsage
from .models.app_setting import AppSetting
from .models.calendar_reminder import CalendarReminder
from .models.country_code import CountryCode
from .models.holiday import Holiday
from .models.ui_settings import UiSettings
from .models.user_settings import UserSettings

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
