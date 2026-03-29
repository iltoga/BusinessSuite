"""
FILE_ROLE: Debug script for inspecting AI usage generation metadata from OpenRouter-backed tasks.

KEY_COMPONENTS:
- _fetch_openrouter_generation_data: Imported helper used to fetch generation details for a known generation id.

INTERACTIONS:
- Depends on: Django settings bootstrap, core.tasks.ai_usage helper, and OpenRouter generation lookup behavior.

AI_GUIDELINES:
- Keep this as a local diagnostic script, not production application logic.
- Do not add business rules or long-running workflows here; use the task/service layer instead.
"""

import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "business_suite.settings.dev")
django.setup()

from core.tasks.ai_usage import _fetch_openrouter_generation_data

try:
    print(_fetch_openrouter_generation_data("gen-1773535395-ROlqfhe8zyc6sDpycDCI"))
except Exception as e:
    print("ERROR:", repr(e))
