from api.permissions import ADMIN_GROUP_NAME
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Force create/update a superuser and ensure membership in the 'admin' group."

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Username for the superuser")
        parser.add_argument("password", type=str, help="Password for the superuser")
        parser.add_argument(
            "--email",
            type=str,
            default="info@example.com",
            help="Email for the superuser (default: info@example.com)",
        )

    def handle(self, *args, **options):
        username = str(options.get("username") or "").strip()
        password = str(options.get("password") or "")
        email = str(options.get("email") or "info@example.com").strip()

        if not username:
            raise CommandError("username is required")
        if not password:
            raise CommandError("password is required")

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={"email": email},
        )

        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        admin_group, group_created = Group.objects.get_or_create(name=ADMIN_GROUP_NAME)
        if not user.groups.filter(name=ADMIN_GROUP_NAME).exists():
            user.groups.add(admin_group)

        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"Superuser upserted: username={user.username} "
                    f"created={created} admin_group_created={group_created}"
                )
            )
        )
