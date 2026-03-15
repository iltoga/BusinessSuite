import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'business_suite.settings.dev')
os.environ.setdefault('SECRET_KEY', 'django-insecure-dev-only')
django.setup()

from customers.tasks import check_passport_uploadability_task
import base64

with open('../business_suite/files/media/tmpfiles/passport_big.jpg', 'rb') as f:
    img_data = f.read()
    b64 = base64.b64encode(img_data).decode('utf-8')

print("Sync executing dramatiq task directly to capture exception output inside python process...")
check_passport_uploadability_task(file_base64=b64, filename="passport_big.jpg", customer_id="1", method="ai", job_id="test")
