from django.apps import AppConfig


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
        from core.tasks import cron_jobs, document_ocr, ocr  # noqa: F401

        # Register models with django-auditlog automatically for apps listed in LOGGING_MODE
        try:
            from auditlog.registry import auditlog
            from django.apps import apps as django_apps

            LOGGING_APPS = globals().get("LOGGING_MODE", ()) or ()
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
