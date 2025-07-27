import glob
import os

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Deletes all the migration files"

    def handle(self, *args, **options):
        migrations_folder = os.path.join("**", "migrations", "*.py")
        # glob.glob returns a list of paths matching a pathname pattern
        for file in glob.glob(migrations_folder, recursive=True):
            # exclude core app migrations (custom migrations added manually) and __init__.py files
            if not file.startswith("core") and not file.endswith("__init__.py"):
                os.remove(file)
                self.stdout.write(self.style.SUCCESS("Successfully deleted file %s" % file))
