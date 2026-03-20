from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "business_suite.settings.dev")
os.environ.setdefault("SECRET_KEY", "django-insecure-dev-only")

import django
from django.test import SimpleTestCase

django.setup()

from core.models.async_job import AsyncJob
from customers.tasks import check_passport_uploadability_task


@dataclass
class FakeAsyncJob:
    job_id: str
    status: str = AsyncJob.STATUS_PENDING
    progress: int = 0
    message: str | None = None
    result: dict | None = None
    error_message: str | None = None
    traceback: str | None = None
    updates: list[SimpleNamespace] = field(default_factory=list)

    def update_progress(self, progress: int, message: str | None = None, status: str | None = None) -> None:
        self.progress = progress
        if message is not None:
            self.message = message
        if status is not None:
            self.status = status
        self.updates.append(SimpleNamespace(progress=progress, message=message, status=status))

    def complete(self, result=None, message: str = "Completed") -> None:
        self.status = AsyncJob.STATUS_COMPLETED
        self.progress = 100
        self.result = result
        self.message = message

    def fail(self, error_message, traceback=None) -> None:
        self.status = AsyncJob.STATUS_FAILED
        self.progress = 100
        self.error_message = error_message
        self.traceback = traceback


@dataclass
class FakeUploadabilityResult:
    is_valid: bool
    method_used: str
    rejection_reason: str | None = None
    rejection_reasons: list[str] | None = None
    rejection_code: str | None = None
    passport_data: dict | None = None
    model_used: str | None = None


class FakePassportUploadabilityService:
    def check_passport(self, file_content: bytes, method: str = "hybrid", progress_callback=None) -> FakeUploadabilityResult:
        if progress_callback is not None:
            progress_callback(35, "Fake Step 2/4: Stub validation setup...")
            progress_callback(60, "Fake Step 3/4: Stub AI validation...")
            progress_callback(82, "Fake Step 4/4: Stub decision synthesis...")
        return FakeUploadabilityResult(
            is_valid=True,
            method_used=f"{method}-stub",
            model_used="stub-model",
            passport_data={
                "passport_number": "X1234567",
                "first_name": "Smoke",
                "last_name": "Test",
                "nationality_code": "IDN",
            },
        )


class CheckPassportUploadabilityTaskTestCase(SimpleTestCase):
    def test_call_local_completes_job_with_stubbed_dependencies(self):
        storage_path = "test_passport_uploadability_task/passport_big.jpg"
        image_bytes = b"fake passport bytes"
        fake_job = FakeAsyncJob(job_id="smoke_passport_dramatiq")

        with (
            patch("customers.tasks.AsyncJob.objects.get", return_value=fake_job),
            patch("customers.tasks.PassportUploadabilityService", new=FakePassportUploadabilityService),
            patch(
                "customers.tasks._build_customer_match_payload",
                return_value={
                    "status": "no_match",
                    "message": "Stubbed customer match for smoke test.",
                    "passport_number": "X1234567",
                    "exact_matches": [],
                    "similar_matches": [],
                    "recommended_action": "create_customer",
                },
            ),
            patch("customers.tasks.default_storage.exists", return_value=True) as exists_mock,
            patch(
                "customers.tasks.default_storage.open",
                return_value=BytesIO(image_bytes),
            ) as open_mock,
            patch("customers.tasks.default_storage.delete") as delete_mock,
        ):
            check_passport_uploadability_task.call_local(fake_job.job_id, storage_path, "ai")

        self.assertEqual(fake_job.status, AsyncJob.STATUS_COMPLETED)
        self.assertEqual(fake_job.progress, 100)
        self.assertIsNone(fake_job.error_message)
        self.assertEqual(fake_job.message, "Passport verified successfully.")
        self.assertIsInstance(fake_job.result, dict)
        self.assertTrue(fake_job.result["is_valid"])
        self.assertEqual(fake_job.result["method_used"], "ai-stub")
        self.assertEqual(fake_job.result["model_used"], "stub-model")
        self.assertEqual(fake_job.result["passport_data"]["passport_number"], "X1234567")
        self.assertEqual(fake_job.result["customer_match"]["status"], "no_match")
        self.assertGreaterEqual(len(fake_job.updates), 5)
        exists_mock.assert_called_once_with(storage_path)
        open_mock.assert_called_once_with(storage_path, "rb")
        delete_mock.assert_called_once_with(storage_path)
