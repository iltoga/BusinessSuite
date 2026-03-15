import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'business_suite.settings.dev')
os.environ.setdefault('SECRET_KEY', 'django-insecure-dev-only')
django.setup()

from core.services.ai_client import AIClient
from core.services.ai_passport_parser import AIPassportParser

print("Testing AIPassportParser._call_vision_api with qwen/qwen3.5-flash-02-23")
parser = AIPassportParser(model="qwen/qwen3.5-flash-02-23", use_openrouter=True)

with open('../business_suite/files/media/tmpfiles/passport_big.jpg', 'rb') as f:
    img_data = f.read()

try:
    res = parser._call_vision_api(img_data, "passport_big.jpg", parser._build_vision_prompt())
    print("Success:", res.success)
    if res.success:
        print("Data:", res.passport_data)
    else:
        print("Error:", res.error_message)
except Exception as e:
    print("Exception thrown:", type(e), e)
