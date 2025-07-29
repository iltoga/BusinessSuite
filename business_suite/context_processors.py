from business_suite.settings.base import GLOBAL_SETTINGS


def site_info(request):
    return {
        "SITE_NAME": GLOBAL_SETTINGS.get("SITE_NAME", "Business Suite"),
        "SITE_DESCRIPTION": GLOBAL_SETTINGS.get("SITE_DESCRIPTION", ""),
    }
