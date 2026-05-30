"""
FILE_ROLE: Serves the public app configuration endpoint for the backend core app.

KEY_COMPONENTS:
- public_app_config: Returns runtime configuration consumed by the Angular frontend.

INTERACTIONS:
- Depends on: core.services.app_setting_service, core.services.google_calendar_event_colors, core.services.ui_settings_service, django.conf.settings
- Consumed by: frontend bootstrap/config loading and feature-flag initialization.

AI_GUIDELINES:
- Keep this endpoint plain Django JSON, not DRF Response, because the frontend boot path expects a lightweight public config payload.
- Do not add write operations or cross-model orchestration here; use services if the payload needs more computation.
- Keep startup/migration error handling defensive so bootstrap can still succeed when tables are not ready.
"""

import logging

from api.permissions import ADMIN_GROUP_NAME, MANAGER_GROUP_NAME
from core.services.app_setting_service import AppSettingScope, AppSettingService
from core.services.google_calendar_event_colors import GoogleCalendarEventColors
from core.services.ui_settings_service import UiSettingsService
from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

DEFAULT_UI_SCALE_PERCENT = 100
MIN_UI_SCALE_PERCENT = 25
MAX_UI_SCALE_PERCENT = 125
DEFAULT_UI_AUTO_SCALE_ENABLED = False
DEFAULT_UI_AUTO_SCALE_REFERENCE_WIDTH = 1440
MIN_UI_AUTO_SCALE_REFERENCE_WIDTH = 1024
DEFAULT_UI_AUTO_SCALE_MIN_PERCENT = 95
DEFAULT_UI_AUTO_SCALE_MAX_PERCENT = 105
MIN_UI_AUTO_SCALE_PERCENT = 25
MAX_UI_AUTO_SCALE_PERCENT = 125
DEFAULT_UI_AUTO_SCALE_DESKTOP_ONLY = True


def _normalize_ui_scale_percent(value):
    try:
        numeric_value = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_UI_SCALE_PERCENT

    return max(MIN_UI_SCALE_PERCENT, min(MAX_UI_SCALE_PERCENT, numeric_value))


def _parse_bool_like(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized_value = value.strip().lower()
        if normalized_value in {"true", "1", "yes", "on"}:
            return True
        if normalized_value in {"false", "0", "no", "off"}:
            return False
    return default


def _normalize_ui_auto_scale_reference_width(value):
    try:
        numeric_value = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_UI_AUTO_SCALE_REFERENCE_WIDTH

    return max(MIN_UI_AUTO_SCALE_REFERENCE_WIDTH, numeric_value)


def _normalize_ui_auto_scale_min_percent(value):
    try:
        numeric_value = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_UI_AUTO_SCALE_MIN_PERCENT

    return max(MIN_UI_AUTO_SCALE_PERCENT, min(100, numeric_value))


def _normalize_ui_auto_scale_max_percent(value):
    try:
        numeric_value = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_UI_AUTO_SCALE_MAX_PERCENT

    return max(100, min(MAX_UI_AUTO_SCALE_PERCENT, numeric_value))


def _normalize_ui_auto_scale_desktop_only(value):
    return _parse_bool_like(value, DEFAULT_UI_AUTO_SCALE_DESKTOP_ONLY)


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
        frontend_raw = AppSettingService.get_scoped_values(scopes={AppSettingScope.FRONTEND, AppSettingScope.BOTH})
        frontend_setting_overrides = {
            key: AppSettingService.parse_json_like(value) for key, value in frontend_raw.items()
        }
    except Exception:
        frontend_setting_overrides = {}

    payload = {
        "MOCK_AUTH_ENABLED": AppSettingService.parse_bool(
            AppSettingService.get_effective_raw("MOCK_AUTH_ENABLED", False), False
        ),
        "DEBUG": bool(settings.DEBUG),
        "useOverlayMenu": use_overlay_menu,
        "title": global_settings.get("SITE_NAME", "BusinessSuite"),
        "dateFormat": str(AppSettingService.get_effective_raw("DATE_FORMAT_JS", "dd-MM-yyyy") or "dd-MM-yyyy"),
        "baseCurrency": str(AppSettingService.get_effective_raw("BASE_CURRENCY", "IDR") or "IDR"),
        "skeletonDebounceDurationMs": int(AppSettingService.get_effective_raw("SKELETON_DEBOUNCE_DURATION_MS", 500)),
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
    payload["rbac"] = {
        "adminGroupName": ADMIN_GROUP_NAME,
        "managerGroupName": MANAGER_GROUP_NAME,
    }
    payload.update(frontend_setting_overrides)

    ui_scale_percent_raw = payload.get(
        "UI_SCALE_PERCENT",
        payload.get(
            "uiScalePercent",
            AppSettingService.get_effective_raw("UI_SCALE_PERCENT", DEFAULT_UI_SCALE_PERCENT),
        ),
    )
    ui_auto_scale_enabled_raw = payload.get(
        "UI_AUTO_SCALE_ENABLED",
        payload.get(
            "uiAutoScaleEnabled",
            AppSettingService.get_effective_raw("UI_AUTO_SCALE_ENABLED", DEFAULT_UI_AUTO_SCALE_ENABLED),
        ),
    )
    ui_auto_scale_reference_width_raw = payload.get(
        "UI_AUTO_SCALE_REFERENCE_WIDTH",
        payload.get(
            "uiAutoScaleReferenceWidth",
            AppSettingService.get_effective_raw("UI_AUTO_SCALE_REFERENCE_WIDTH", DEFAULT_UI_AUTO_SCALE_REFERENCE_WIDTH),
        ),
    )
    ui_auto_scale_min_percent_raw = payload.get(
        "UI_AUTO_SCALE_MIN_PERCENT",
        payload.get(
            "uiAutoScaleMinPercent",
            AppSettingService.get_effective_raw("UI_AUTO_SCALE_MIN_PERCENT", DEFAULT_UI_AUTO_SCALE_MIN_PERCENT),
        ),
    )
    ui_auto_scale_max_percent_raw = payload.get(
        "UI_AUTO_SCALE_MAX_PERCENT",
        payload.get(
            "uiAutoScaleMaxPercent",
            AppSettingService.get_effective_raw("UI_AUTO_SCALE_MAX_PERCENT", DEFAULT_UI_AUTO_SCALE_MAX_PERCENT),
        ),
    )
    ui_auto_scale_desktop_only_raw = payload.get(
        "UI_AUTO_SCALE_DESKTOP_ONLY",
        payload.get(
            "uiAutoScaleDesktopOnly",
            AppSettingService.get_effective_raw("UI_AUTO_SCALE_DESKTOP_ONLY", DEFAULT_UI_AUTO_SCALE_DESKTOP_ONLY),
        ),
    )

    ui_auto_scale_min_percent = _normalize_ui_auto_scale_min_percent(ui_auto_scale_min_percent_raw)
    ui_auto_scale_max_percent = _normalize_ui_auto_scale_max_percent(ui_auto_scale_max_percent_raw)
    if ui_auto_scale_max_percent < ui_auto_scale_min_percent:
        ui_auto_scale_max_percent = ui_auto_scale_min_percent

    payload["uiScalePercent"] = _normalize_ui_scale_percent(ui_scale_percent_raw)
    payload["uiAutoScaleEnabled"] = _parse_bool_like(
        ui_auto_scale_enabled_raw,
        DEFAULT_UI_AUTO_SCALE_ENABLED,
    )
    payload["uiAutoScaleReferenceWidth"] = _normalize_ui_auto_scale_reference_width(ui_auto_scale_reference_width_raw)
    payload["uiAutoScaleMinPercent"] = ui_auto_scale_min_percent
    payload["uiAutoScaleMaxPercent"] = ui_auto_scale_max_percent
    payload["uiAutoScaleDesktopOnly"] = _normalize_ui_auto_scale_desktop_only(ui_auto_scale_desktop_only_raw)

    return JsonResponse(payload)
