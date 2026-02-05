from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Drop django-easyaudit database tables by migrating the app to zero (non-destructive by default)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            dest="yes",
            help="Apply the migration to zero (permanently remove easyaudit tables).",
        )

    def handle(self, *args, **options):
        if "easyaudit" not in settings.INSTALLED_APPS:
            self.stdout.write("easyaudit is not present in INSTALLED_APPS; nothing to do.")
            return

        if not options.get("yes"):
            self.stdout.write("Dry-run: easyaudit is present. Run with --yes to migrate to zero.")
            return

        # Apply the migration to zero
        call_command("migrate", "easyaudit", "zero")
        self.stdout.write("Successfully migrated easyaudit to zero")
