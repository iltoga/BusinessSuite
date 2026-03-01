"""
Custom management command to enqueue scheduled jobs via PgQueuer.
This command queues the same jobs that are scheduled periodically.
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.services.logger_service import Logger

logger = Logger.get_logger(__name__)


class Command(BaseCommand):
    help = "Queue scheduled jobs manually via PgQueuer"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            help="Force run all cron jobs regardless of schedule",
        )

    def handle(self, *args, **options):
        """Execute all cron jobs."""
        from core.tasks.cron_jobs import (
            enqueue_clear_cache_now,
            enqueue_full_backup_now,
            enqueue_run_auditlog_prune_now,
            enqueue_run_openrouter_health_check_now,
        )

        force = options.get("force", False)

        cron_jobs = [
            ("FullBackupJob", enqueue_full_backup_now),
            ("ClearCacheJob", enqueue_clear_cache_now),
            ("AuditlogPruneJob", enqueue_run_auditlog_prune_now),
            ("OpenRouterHealthCheckJob", enqueue_run_openrouter_health_check_now),
        ]

        self.stdout.write(self.style.SUCCESS(f"Starting cron jobs execution at {timezone.now()}"))

        queued_count = 0
        skipped_count = 0
        error_count = 0

        for job_name, enqueue_callable in cron_jobs:
            try:
                self.stdout.write(f"Running {job_name}...")
                result = enqueue_callable()
                if result is False:
                    self.stdout.write(self.style.WARNING(f"⚠️  {job_name} already queued/running, skipped"))
                    skipped_count += 1
                    continue

                self.stdout.write(self.style.SUCCESS(f"✅ {job_name} queued successfully"))
                queued_count += 1
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
                f"  - Queued: {queued_count}\n"
                f"  - Skipped: {skipped_count}\n"
                f"  - Failed: {error_count}\n"
                f"  - Completed at: {timezone.now()}"
            )
        )

        if error_count > 0:
            self.stdout.write(self.style.WARNING(f"⚠️  {error_count} job(s) failed. Check the logs for details."))
