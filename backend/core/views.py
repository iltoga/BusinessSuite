import logging

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

    return JsonResponse(
        {
            "MOCK_AUTH_ENABLED": getattr(settings, "MOCK_AUTH_ENABLED", False),
            "useOverlayMenu": use_overlay_menu,
            "title": global_settings.get("SITE_NAME", "BusinessSuite"),
            "dateFormat": getattr(settings, "DATE_FORMAT_JS", "dd-MM-yyyy"),
            "calendarTodoColorId": GoogleCalendarEventColors.todo_color_id(),
            "calendarDoneColorId": GoogleCalendarEventColors.done_color_id(),
            "logoFilename": global_settings.get("LOGO_FILENAME", "logo_transparent.png"),
            "logoInvertedFilename": global_settings.get("LOGO_INVERTED_FILENAME", "logo_inverted_transparent.png"),
        }
    )
