import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from dotenv import load_dotenv

load_dotenv()


class Command(BaseCommand):
    help = "Create a Django superuser if one does not exist"

    def handle(self, *args, **options):
        if User.objects.filter(is_superuser=True).count() == 0:
            print("No superusers exist. Creating a superuser...")
            site_admin_username = os.getenv("SITE_ADMIN_USERNAME", "admin")
            site_admin_email = os.getenv("SITE_ADMIN_EMAIL", "info@example.com")
            site_admin_password = os.getenv("SITE_ADMIN_PASSWORD", "P12345678!")
            user = User.objects.create_superuser(site_admin_username, site_admin_email, site_admin_password)
            # print the user's data
            print("Superuser created:")
            print("Username: " + user.username)
            print("Email: " + user.email)
            print("Password: " + site_admin_password)

        else:
            print("A superuser exists. Skipping createsuperuser command.")
