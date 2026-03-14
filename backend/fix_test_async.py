import asyncio
from django.test import AsyncClient
from django.urls import reverse
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model

User = get_user_model()
client = AsyncClient()
print("AsyncClient available in Django test framework")
