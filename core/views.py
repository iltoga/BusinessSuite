import logging

from django.conf import settings
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
    return JsonResponse(
        {
            "MOCK_AUTH_ENABLED": getattr(settings, "MOCK_AUTH_ENABLED", False),
            "title": global_settings.get("SITE_NAME", "BusinessSuite"),
            "dateFormat": getattr(settings, "DATE_FORMAT_JS", "dd-MM-yyyy"),
            "logoFilename": global_settings.get("LOGO_FILENAME", "logo_transparent.png"),
            "logoInvertedFilename": global_settings.get("LOGO_INVERTED_FILENAME", "logo_inverted_transparent.png"),
        }
    )
