from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Create a Django superuser if one does not exist'

    def handle(self, *args, **options):
        if User.objects.filter(is_superuser=True).count() == 0:
            print("No superusers exist. Creating a superuser...")
            user = User.objects.create_superuser('revisadmin', 'info@revisbali.com', 'Password123!')
            # print the user's data
            print("Superuser created:")
            print("Username: " + user.username)
            print("Email: " + user.email)
            print("Password: " + 'Password123!')

        else:
            print("A superuser exists. Skipping createsuperuser command.")
