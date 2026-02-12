import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from core.services.google_calendar_event_colors import GoogleCalendarEventColors


def public_app_config(request):
    """
    Returns public application configuration (e.g. MOCK_AUTH_ENABLED)
    derived from backend settings/environment.
    Used by Angular frontend to synchronize behavior with backend.
    """
    # Ensure it's a regular Django response, not DRF Response
    global_settings = getattr(settings, "GLOBAL_SETTINGS", {})
    return JsonResponse(
        {
            "MOCK_AUTH_ENABLED": getattr(settings, "MOCK_AUTH_ENABLED", False),
            "title": global_settings.get("SITE_NAME", "BusinessSuite"),
            "dateFormat": getattr(settings, "DATE_FORMAT_JS", "dd-MM-yyyy"),
            "calendarTodoColorId": GoogleCalendarEventColors.todo_color_id(),
            "calendarDoneColorId": GoogleCalendarEventColors.done_color_id(),
            "logoFilename": global_settings.get("LOGO_FILENAME", "logo_transparent.png"),
            "logoInvertedFilename": global_settings.get("LOGO_INVERTED_FILENAME", "logo_inverted_transparent.png"),
            "fcmSenderId": getattr(settings, "FCM_SENDER_ID", ""),
            "fcmVapidPublicKey": getattr(settings, "FCM_VAPID_PUBLIC_KEY", ""),
            "fcmProjectId": getattr(settings, "FCM_PROJECT_ID", ""),
            "fcmProjectNumber": getattr(settings, "FCM_PROJECT_NUMBER", ""),
            "fcmWebApiKey": getattr(settings, "FCM_WEB_API_KEY", ""),
            "fcmWebAppId": getattr(settings, "FCM_WEB_APP_ID", ""),
            "fcmWebAuthDomain": getattr(settings, "FCM_WEB_AUTH_DOMAIN", ""),
            "fcmWebStorageBucket": getattr(settings, "FCM_WEB_STORAGE_BUCKET", ""),
            "fcmWebMeasurementId": getattr(settings, "FCM_WEB_MEASUREMENT_ID", ""),
        }
    )
