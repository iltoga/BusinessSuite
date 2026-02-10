import os

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS, IntegrityError, connections, transaction
from django.db.models import signals


class Command(BaseCommand):
    help = "Migrate data from PostgreSQL to SQLite"

    def add_arguments(self, parser):
        parser.add_argument("sqlite_db", nargs="?", type=str, default=None, help="Name of the SQLite database")

    def handle(self, *args, **options):
        sqlite_db = options["sqlite_db"]

        # Check if the sqlite_db argument was provided
        if sqlite_db is None:
            sqlite_db = "db.sqlite3"

        # Configure Django to use the new SQLite database
        sqlite_db_path = os.path.join(settings.BASE_DIR, f"files/{sqlite_db}")
        connections.databases[sqlite_db] = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": sqlite_db_path,
            "TIME_ZONE": settings.TIME_ZONE,
            "CONN_MAX_AGE": getattr(settings, "CONN_MAX_AGE", 0),
            "CONN_HEALTH_CHECKS": getattr(settings, "CONN_HEALTH_CHECKS", {}),
            "OPTIONS": getattr(settings, "OPTIONS", {}),
            "AUTOCOMMIT": getattr(settings, "AUTOCOMMIT", True),
        }

        # Run the migrate command to create the SQLite database schema
        call_command("migrate", database=sqlite_db)

        # Disable foreign key constraints
        with connections[sqlite_db].cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = OFF;")

        # Disable signals
        signals.pre_save.receivers = []
        signals.post_save.receivers = []

        # Get all installed Django apps
        for app in apps.get_app_configs():
            print(f"Migrating app {app.name}")
            for model in app.get_models():
                print(f"Migrating model {model.__name__}")
                with transaction.atomic():
                    for obj in model.objects.using(DEFAULT_DB_ALIAS).all():
                        try:
                            obj.save(using=sqlite_db)  # save it to the SQLite database
                        except IntegrityError as e:
                            print(f"Failed to save object {obj}: {e}")

        # Enable foreign key constraints
        with connections[sqlite_db].cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = ON;")
