import logging

from core.services.app_setting_service import AppSettingScope, AppSettingService
from core.services.google_calendar_event_colors import GoogleCalendarEventColors
from core.services.ui_settings_service import UiSettingsService
from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


def public_app_config(request):
    """
    Returns public application configuration (e.g. MOCK_AUTH_ENABLED)
    derived from backend settings/environment.
    Used by Angular frontend to synchronize behavior with backend.
    """
    # Ensure it's a regular Django response, not DRF Response
    global_settings = getattr(settings, "GLOBAL_SETTINGS", {})
    use_overlay_menu = False
    try:
        use_overlay_menu = bool(UiSettingsService.get_settings().use_overlay_menu)
    except (OperationalError, ProgrammingError):
        # DB table may not exist yet during initial startup/migrations.
        use_overlay_menu = False

    frontend_setting_overrides: dict[str, object] = {}
    try:
        frontend_raw = AppSettingService.get_scoped_values(
            scopes={AppSettingScope.FRONTEND, AppSettingScope.BOTH}
        )
        frontend_setting_overrides = {
            key: AppSettingService.parse_json_like(value) for key, value in frontend_raw.items()
        }
    except Exception:
        frontend_setting_overrides = {}

    payload = {
        "MOCK_AUTH_ENABLED": AppSettingService.parse_bool(AppSettingService.get_effective_raw("MOCK_AUTH_ENABLED", False), False),
        "useOverlayMenu": use_overlay_menu,
        "title": global_settings.get("SITE_NAME", "BusinessSuite"),
        "dateFormat": str(AppSettingService.get_effective_raw("DATE_FORMAT_JS", "dd-MM-yyyy") or "dd-MM-yyyy"),
        "baseCurrency": str(AppSettingService.get_effective_raw("BASE_CURRENCY", "IDR") or "IDR"),
        "calendarTodoColorId": GoogleCalendarEventColors.todo_color_id(),
        "calendarDoneColorId": GoogleCalendarEventColors.done_color_id(),
        "fcmSenderId": global_settings.get("FCM_SENDER_ID", settings.FCM_SENDER_ID),
        "fcmVapidPublicKey": global_settings.get("FCM_VAPID_PUBLIC_KEY", settings.FCM_VAPID_PUBLIC_KEY),
        "fcmProjectId": global_settings.get("FCM_PROJECT_ID", settings.FCM_PROJECT_ID),
        "fcmProjectNumber": global_settings.get("FCM_PROJECT_NUMBER", settings.FCM_PROJECT_NUMBER),
        "fcmWebApiKey": global_settings.get("FCM_WEB_API_KEY", settings.FCM_WEB_API_KEY),
        "fcmWebAppId": global_settings.get("FCM_WEB_APP_ID", settings.FCM_WEB_APP_ID),
        "fcmWebAuthDomain": global_settings.get("FCM_WEB_AUTH_DOMAIN", settings.FCM_WEB_AUTH_DOMAIN),
        "fcmWebStorageBucket": global_settings.get("FCM_WEB_STORAGE_BUCKET", settings.FCM_WEB_STORAGE_BUCKET),
        "fcmWebMeasurementId": global_settings.get("FCM_WEB_MEASUREMENT_ID", settings.FCM_WEB_MEASUREMENT_ID),
    }
    payload.update(frontend_setting_overrides)

    return JsonResponse(payload)
