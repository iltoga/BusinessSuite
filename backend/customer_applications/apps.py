from django.apps import AppConfig


class DocsWorkflowConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'customer_applications'

    def ready(self):
        # Import signals to connect them when the app is ready
        from customer_applications.hooks import signals  # noqa: F401
