from rest_framework import authentication
from django.conf import settings
from django.contrib.auth.models import User

class BearerAuthentication(authentication.TokenAuthentication):
    keyword = 'Bearer'

    def authenticate_credentials(self, key):
        if getattr(settings, 'MOCK_AUTH_ENABLED', False) and key == 'mock-token':
            # Use get_or_create to get or create a mock user for development
            user, _ = User.objects.get_or_create(
                username='mockuser',
                defaults={
                    'is_staff': True,
                    'is_superuser': True,
                    'email': 'mock@example.com'
                }
            )
            # Ensure the user is active and has staff/superuser permissions
            if not user.is_staff or not user.is_superuser:
                user.is_staff = True
                user.is_superuser = True
                user.save()
            return (user, None)
        return super().authenticate_credentials(key)
