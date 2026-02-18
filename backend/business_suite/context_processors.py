from business_suite.settings import base as settings


def site_info(request):
    return {
        "SITE_NAME": settings.GLOBAL_SETTINGS.get("SITE_NAME", "Business Suite"),
        "SITE_DESCRIPTION": settings.GLOBAL_SETTINGS.get("SITE_DESCRIPTION", ""),
        "LOGO_FILENAME": settings.GLOBAL_SETTINGS.get("LOGO_FILENAME", "logo_transparent.png"),
        "LOGO_INVERTED_FILENAME": settings.GLOBAL_SETTINGS.get(
            "LOGO_INVERTED_FILENAME", "logo_inverted_transparent.png"
        ),
        # Make the flag available to templates so they can switch layouts
        "DISABLE_DJANGO_VIEWS": getattr(settings, "DISABLE_DJANGO_VIEWS", False),
        # Provide a base template variable to allow templates to switch layouts easily
        "BASE_PARENT_TEMPLATE": (
            "bootstrap_base.html" if getattr(settings, "DISABLE_DJANGO_VIEWS", False) else "base_template.html"
        ),
    }
