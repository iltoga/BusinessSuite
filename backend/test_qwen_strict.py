import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'business_suite.settings.dev')
django.setup()

from core.services.ai_client import AIClient
from core.services.ai_passport_parser import AIPassportParser

parser = AIPassportParser(model="qwen/qwen3.5-flash-02-23", use_openrouter=True)
client = parser.ai_client

with open('../business_suite/files/media/tmpfiles/passport_big.jpg', 'rb') as f:
    img_data = f.read()

messages = client.build_vision_message(
    prompt="test",
    image_bytes=img_data,
    filename="test.jpg",
    system_prompt="test",
)

try:
    print("Testing chat_completion_json directly with extra_body...")
    res = client.chat_completion_json(messages=messages, json_schema=parser.PASSPORT_SCHEMA, schema_name="passport_data")
    print("Success!")
except Exception as e:
    print(f"FAILED: {type(e).__name__} - {e}")
    if hasattr(e, 'error_code'):
        print("ErrorCode:", e.error_code)

