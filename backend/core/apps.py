from core.services.logger_service import Logger
from django.apps import AppConfig

logger = Logger.get_logger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Removed easyaudit-specific monkey-patch: the project no longer relies on easyaudit
        # and the problematic transaction atomic patch is not needed. If easyaudit is still
        # installed in an environment, admins should run `python manage.py migrate easyaudit zero`
        # before removing the package entirely.
        pass

        # Ensure Huey tasks are registered and we register our own signals after the patch
        # so that our signal handlers integrate with the patched behavior.
        # Register our signal forwarder (if present)
        import core.signals  # noqa: F401
        import core.signals_calendar  # noqa: F401
        import core.signals_calendar_reminder  # noqa: F401
        import core.sync_signals  # noqa: F401
        import core.telemetry.huey_tracing  # noqa: F401
        from core.tasks import (  # noqa: F401
            ai_usage,
            calendar_reminders,
            calendar_sync,
            cron_jobs,
            document_ocr,
            local_resilience,
            ocr,
        )

        # Register models with django-auditlog automatically for apps listed in LOGGING_MODE
        try:
            from auditlog.registry import auditlog
            from django.apps import apps as django_apps
            from django.conf import settings

            # Support existing setting name `LOGGING_MODELS` (plural) for backward compatibility
            LOGGING_APPS = getattr(settings, "LOGGING_MODE", None) or getattr(settings, "LOGGING_MODELS", ()) or ()
            for app_label in LOGGING_APPS:
                try:
                    app_config = django_apps.get_app_config(app_label)
                except LookupError:
                    continue
                for model in app_config.get_models():
                    try:
                        auditlog.register(model)
                    except Exception:
                        # ignore duplicate registrations or missing auditlog
                        continue
        except Exception:
            # auditlog not installed or registration failed — ignore
            pass

        # Ensure our OpenAPI extensions are imported so drf-spectacular can discover them
        try:
            import core.openapi  # noqa: F401
        except Exception:
            # if import fails, don't abort startup — this only affects documentation generation
            pass
