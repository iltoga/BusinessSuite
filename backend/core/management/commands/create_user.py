"""
FILE_ROLE: Django management command for the core app.

KEY_COMPONENTS:
- Command: Module symbol.

INTERACTIONS:
- Depends on: core models, Django migration/management machinery, and related app services imported by this module.

AI_GUIDELINES:
- Keep command logic thin and delegate real work to services when possible.
- Keep migrations schema-only and reversible; do not add runtime business logic here.
"""

import logging

# file logger in prod and console in dev
from core.services.logger_service import Logger
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

logger = Logger.get_logger(__name__)


class Command(BaseCommand):
    help = "Create a default user"

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Username for the new user")
        parser.add_argument("password", type=str, help="Password for the new user")
        parser.add_argument("--staff", action="store_true", help="Create a staff user")
        parser.add_argument("--superuser", action="store_true", help="Create a superuser")
        parser.add_argument("--inactive", dest="active", action="store_false", help="Create an inactive user")
        parser.add_argument("--email", type=str, help="Email address for the new user")

    def handle(self, *args, **options):
        username = options.pop("username")
        password = options.pop("password")

        self.create_user(username, password, **options)

    def create_user(self, username, password, **options):
        is_staff = options.get("staff", False)
        is_superuser = options.get("superuser", False)
        is_active = options.get("active", True)
        email = options.get("email", None)

        UserModel = get_user_model()

        if not UserModel.objects.filter(username=username).exists():
            user = UserModel.objects.create_user(username, password=password)
            user.is_superuser = is_superuser
            user.is_staff = is_staff
            user.is_active = is_active
            if email:
                user.email = email
            user.save()
            logger.info(f"User {username} has been created")
