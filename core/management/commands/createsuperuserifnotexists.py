from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Create a Django superuser if one does not exist'

    def handle(self, *args, **options):
        if User.objects.filter(is_superuser=True).count() == 0:
            print("No superusers exist. Creating a superuser...")
            User.objects.create_superuser('revisadmin', 'info@revisbali.com', 'Password123!')
        else:
            print("A superuser exists. Skipping createsuperuser command.")
