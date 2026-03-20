from __future__ import annotations

import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_ROOT.parent
OUTPUT_DIR = SCRIPT_DIR / "outputs"


def bootstrap_django() -> None:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "business_suite.settings.dev")
    os.environ.setdefault("SECRET_KEY", "django-insecure-dev-only")

    import django

    django.setup()


def output_path(filename: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / filename
