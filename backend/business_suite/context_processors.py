"""
FILE_ROLE: Template context processors for site-level branding and metadata.

KEY_COMPONENTS:
- site_info: Module symbol.

INTERACTIONS:
- Depends on: Django settings/bootstrap and adjacent app services or middleware in this module.

AI_GUIDELINES:
- Keep the file focused on its narrow responsibility and avoid mixing in unrelated business logic.
- Preserve existing runtime contracts for middleware, scripts, or migrations because other code depends on them.
"""

from business_suite.settings import base as settings


def site_info(request):
    return {
        "SITE_NAME": settings.GLOBAL_SETTINGS.get("SITE_NAME", "Business Suite"),
        "SITE_DESCRIPTION": settings.GLOBAL_SETTINGS.get("SITE_DESCRIPTION", ""),
        "LOGO_FILENAME": settings.GLOBAL_SETTINGS.get("LOGO_FILENAME", "logo_transparent.png"),
        "LOGO_INVERTED_FILENAME": settings.GLOBAL_SETTINGS.get(
            "LOGO_INVERTED_FILENAME", "logo_inverted_transparent.png"
        ),
    }
