"""
FILE_ROLE: Standalone development script for manual backend diagnostics.

KEY_COMPONENTS:
- main: Script entrypoint.

INTERACTIONS:
- Depends on: dev_scripts._bootstrap and the passport Dramatiq workflow.

AI_GUIDELINES:
- Keep the script focused on local diagnostics and avoid production application logic.
- Preserve the manual request/response flow because it is used for ad hoc backend checks.
"""

from __future__ import annotations

import base64
import logging
import sys

from _bootstrap import REPO_ROOT, bootstrap_django

logging.basicConfig(level=logging.INFO, stream=sys.stdout)


def main() -> None:
    bootstrap_django()

    from core.models.async_job import AsyncJob
    from customers.tasks import check_passport_uploadability_task

    passport_path = REPO_ROOT / "business_suite" / "files" / "media" / "tmpfiles" / "passport_big.jpg"
    with passport_path.open("rb") as f:
        img_data = f.read()
    b64 = base64.b64encode(img_data).decode("utf-8")

    job = AsyncJob.objects.create(name="test_passport_workflow", status="pending")

    print(f"Executing dramatiq task directly with Job ID: {job.id} ...")
    try:
        check_passport_uploadability_task(
            file_base64=b64,
            filename="passport_big.jpg",
            customer_id="1",
            method="ai",
            job_id=str(job.id),
        )

        job.refresh_from_db()
        print("FINAL JOB STATUS:", job.status)
        print("FINAL JOB RESULT:", job.result)
        print("FINAL JOB ERROR:", job.error_message)
    except Exception as e:
        print("CAUGHT EXCEPTION:", e)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
