"""
FILE_ROLE: Django app configuration for the admin tools app.

KEY_COMPONENTS:
- AdminToolsConfig: Django app config.

INTERACTIONS:
- Depends on: Django settings/bootstrap and adjacent app services or middleware in this module.

AI_GUIDELINES:
- Keep the file focused on its narrow responsibility and avoid mixing in unrelated business logic.
- Preserve existing runtime contracts for app routing, model behavior, and service boundaries.
"""

from django.apps import AppConfig


class AdminToolsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "admin_tools"
    verbose_name = "Admin Tools"
