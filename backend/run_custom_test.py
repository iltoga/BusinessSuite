import os
import django
import sys
import logging

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'business_suite.settings.dev')
os.environ.setdefault('SECRET_KEY', 'django-insecure-dev-only')
django.setup()

from core.services.ai_passport_parser import AIPassportParser
from core.models.ai_model import AiModel

try:
    print("Testing parser...")
    parser = AIPassportParser(model="qwen/qwen3.5-flash-02-23", use_openrouter=True)
    with open('../business_suite/files/media/tmpfiles/passport_big.jpg', 'rb') as f:
        img_data = f.read()

    print("Calling vision API...")
    res = parser._call_vision_api(img_data, "passport_big.jpg", parser._build_vision_prompt())
    print("RES SUCCESS:", res.success)
    print("RES ERROR:", res.error_message)
except Exception as e:
    print("CAUGHT EXCEPTION:", e)
    import traceback
    traceback.print_exc()
