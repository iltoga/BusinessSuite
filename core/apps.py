from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Ensure Huey tasks are registered
        from core.tasks import cron_jobs, document_ocr, ocr  # noqa: F401
