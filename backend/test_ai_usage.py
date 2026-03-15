import sys
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "business_suite.settings.dev")
django.setup()

from core.tasks.ai_usage import _fetch_openrouter_generation_data
try:
    print(_fetch_openrouter_generation_data("gen-1773535395-ROlqfhe8zyc6sDpycDCI"))
except Exception as e:
    print("ERROR:", repr(e))
