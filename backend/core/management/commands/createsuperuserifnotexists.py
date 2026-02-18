import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from dotenv import load_dotenv

load_dotenv()


class Command(BaseCommand):
    help = "Create a Django superuser if one does not exist and ensure default auth groups"
    REQUIRED_GROUPS = ("admin", "manager", "controller", "agent")

    def _ensure_required_groups(self):
        for group_name in self.REQUIRED_GROUPS:
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                print(f"Group '{group.name}' created.")

    def _assign_admin_group_to_revisadmin(self):
        user_model = get_user_model()
        revisadmin = user_model.objects.filter(username="revisadmin").first()
        if not revisadmin:
            print("User 'revisadmin' not found. Skipping default 'admin' group assignment.")
            return

        admin_group = Group.objects.get(name="admin")
        if revisadmin.groups.filter(name="admin").exists():
            return

        revisadmin.groups.add(admin_group)
        print("Assigned 'admin' group to user 'revisadmin'.")

    def handle(self, *args, **options):
        user_model = get_user_model()

        # Always ensure required groups exist.
        self._ensure_required_groups()

        if user_model.objects.filter(is_superuser=True).count() == 0:
            print("No superusers exist. Creating a superuser...")
            site_admin_username = os.getenv("SITE_ADMIN_USERNAME", "revisadmin")
            site_admin_email = os.getenv("SITE_ADMIN_EMAIL", "info@example.com")
            site_admin_password = os.getenv("SITE_ADMIN_PASSWORD", "P12345678!")
            user = user_model.objects.create_superuser(site_admin_username, site_admin_email, site_admin_password)
            # print the user's data
            print("Superuser created:")
            print("Username: " + user.username)
            print("Email: " + user.email)
            print("Password: " + site_admin_password)

        else:
            print("A superuser exists. Skipping createsuperuser command.")

        # Keep revisadmin as default member of 'admin' group.
        self._assign_admin_group_to_revisadmin()
