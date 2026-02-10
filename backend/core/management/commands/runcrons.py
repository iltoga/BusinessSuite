"""
Custom management command to enqueue scheduled jobs via Huey.
This command queues the same jobs that are scheduled periodically.
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.services.logger_service import Logger

logger = Logger.get_logger(__name__)


class Command(BaseCommand):
    help = "Queue scheduled jobs manually via Huey"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            help="Force run all cron jobs regardless of schedule",
        )

    def handle(self, *args, **options):
        """Execute all cron jobs."""
        from core.tasks.cron_jobs import run_auditlog_prune_now, run_clear_cache_now, run_full_backup_now

        force = options.get("force", False)

        cron_jobs = [
            ("FullBackupJob", run_full_backup_now),
            ("ClearCacheJob", run_clear_cache_now),
            ("AuditlogPruneJob", run_auditlog_prune_now),
        ]

        self.stdout.write(self.style.SUCCESS(f"Starting cron jobs execution at {timezone.now()}"))

        success_count = 0
        error_count = 0

        for job_name, job_task in cron_jobs:
            try:
                self.stdout.write(f"Running {job_name}...")
                job_task.delay()
                self.stdout.write(self.style.SUCCESS(f"✅ {job_name} queued successfully"))
                success_count += 1
            except Exception as e:
                error_message = f"❌ {job_name} failed: {str(e)}"
                self.stdout.write(self.style.ERROR(error_message))
                logger.error(error_message, exc_info=True)
                error_count += 1

        # Summary
        total_jobs = len(cron_jobs)
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCron jobs execution completed:\n"
                f"  - Total jobs: {total_jobs}\n"
                f"  - Successful: {success_count}\n"
                f"  - Failed: {error_count}\n"
                f"  - Completed at: {timezone.now()}"
            )
        )

        if error_count > 0:
            self.stdout.write(self.style.WARNING(f"⚠️  {error_count} job(s) failed. Check the logs for details."))
