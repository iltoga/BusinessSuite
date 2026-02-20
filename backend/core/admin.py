from django.contrib import admin

from .models import AIRequestUsage, CalendarReminder, CountryCode, Holiday, UserSettings

admin.site.register(Holiday)
admin.site.register(CountryCode)
admin.site.register(UserSettings)
admin.site.register(CalendarReminder)


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
