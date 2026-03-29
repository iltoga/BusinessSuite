"""
FILE_ROLE: Debug script for manually querying OpenRouter generation results during AI troubleshooting.

KEY_COMPONENTS:
- requests.get: Performs the HTTP lookup against the OpenRouter generation endpoint.

INTERACTIONS:
- Depends on: Django settings bootstrap, OpenRouter API access, and the requests library.

AI_GUIDELINES:
- Keep this script limited to manual diagnostics and local experimentation.
- Avoid turning it into application code; the reusable behavior belongs in services or tasks.
"""

import os

import django
import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "business_suite.settings.dev")
django.setup()

from django.conf import settings

api_key = settings.OPENROUTER_API_KEY
url = "https://openrouter.ai/api/v1/generation?id=gen-1773535395-ROlqfhe8zyc6sDpycDCI"
headers = {"Authorization": f"Bearer {api_key}"}

resp = requests.get(url, headers=headers)
print("Status:", resp.status_code)
print("Response:", resp.text[:500])
