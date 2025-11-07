from business_suite.settings.base import GLOBAL_SETTINGS


def site_info(request):
    return {
        "SITE_NAME": GLOBAL_SETTINGS.get("SITE_NAME", "Business Suite"),
        "SITE_DESCRIPTION": GLOBAL_SETTINGS.get("SITE_DESCRIPTION", ""),
        "LOGO_FILENAME": GLOBAL_SETTINGS.get("LOGO_FILENAME", "logo_transparent.png"),
        "LOGO_INVERTED_FILENAME": GLOBAL_SETTINGS.get("LOGO_INVERTED_FILENAME", "logo_inverted_transparent.png"),
    }
