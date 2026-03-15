import os
import time

import django
from core.models.async_job import AsyncJob
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "business_suite.settings.dev")
os.environ.setdefault("SECRET_KEY", "django-insecure-dev-only")
django.setup()

from django.contrib.auth.models import User

# Get first user for auth
user = User.objects.first()
if not user:
    print("No users found.")
    exit(1)

client = APIClient()
client.force_authenticate(user=user)

with open("business_suite/files/media/tmpfiles/passport_big.jpg", "rb") as f:
    passport_data = f.read()

print("Sending POST request to /api/customers/check-passport/ ...")
response = client.post(
    "/api/customers/check-passport/",
    {"file": SimpleUploadedFile("passport_big.jpg", passport_data, content_type="image/jpeg"), "method": "ai"},
    format="multipart",
)

print(f"Status: {response.status_code}")
print(f"Response: {response.data}")

if response.status_code == 202:
    job_id = response.data.get("job_id")
    print(f"Got Job ID: {job_id}. Waiting for progress...")

    attempts = 0
    while attempts < 30:
        job = AsyncJob.objects.get(id=job_id)
        print(f"Attempt {attempts+1}: Status={job.status}, Progress={job.progress}")
        if job.status in ["completed", "failed"]:
            print(f"Final Job State: {job.result if job.status == 'completed' else job.error_message}")
            break
        time.sleep(2)
        attempts += 1
