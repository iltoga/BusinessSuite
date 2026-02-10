from django.apps import AppConfig


class InvoicesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "invoices"

    def ready(self):
        from invoices.tasks import document_jobs, import_jobs  # noqa: F401
