import os
import requests
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "business_suite.settings.dev")
django.setup()

from django.conf import settings

api_key = settings.OPENROUTER_API_KEY
url = "https://openrouter.ai/api/v1/generation?id=gen-1773535395-ROlqfhe8zyc6sDpycDCI"
headers = {"Authorization": f"Bearer {api_key}"}

resp = requests.get(url, headers=headers)
print("Status:", resp.status_code)
print("Response:", resp.text[:500])
