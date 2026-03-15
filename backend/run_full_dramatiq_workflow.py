import os
import django
import sys
import logging
import time

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'business_suite.settings.dev')
os.environ.setdefault('SECRET_KEY', 'django-insecure-dev-only')
django.setup()

from customers.tasks import check_passport_uploadability_task
from core.models.async_job import AsyncJob
import base64

with open('../business_suite/files/media/tmpfiles/passport_big.jpg', 'rb') as f:
    img_data = f.read()
    b64 = base64.b64encode(img_data).decode('utf-8')

job = AsyncJob.objects.create(name="test_passport_workflow", status="pending")

print(f"Executing dramatiq task directly with Job ID: {job.id} ...")
try:
    check_passport_uploadability_task(file_base64=b64, filename="passport_big.jpg", customer_id="1", method="ai", job_id=str(job.id))
    
    # Reload job
    job.refresh_from_db()
    print("FINAL JOB STATUS:", job.status)
    print("FINAL JOB RESULT:", job.result)
    print("FINAL JOB ERROR:", job.error_message)

except Exception as e:
    print("CAUGHT EXCEPTION:", e)
    import traceback
    traceback.print_exc()

