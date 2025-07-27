"""
Custom management command to replace django_cron functionality.
This command executes all the cron jobs defined in core/cron.py
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run cron jobs manually (replacement for django_cron runcrons command)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            dest='force',
            help='Force run all cron jobs regardless of schedule',
        )

    def handle(self, *args, **options):
        """Execute all cron jobs."""
        from core.cron import (
            FullBackupJob,
            ClearCacheJob,
        )
        
        force = options.get('force', False)
        
        # List of all cron job classes
        cron_jobs = [
            FullBackupJob,
            ClearCacheJob,
        ]
        
        self.stdout.write(
            self.style.SUCCESS(f'Starting cron jobs execution at {timezone.now()}')
        )
        
        success_count = 0
        error_count = 0
        
        for job_class in cron_jobs:
            job_name = job_class.__name__
            try:
                self.stdout.write(f'Running {job_name}...')
                
                # Create an instance of the job and run it
                job_instance = job_class()
                job_instance.do()
                
                self.stdout.write(
                    self.style.SUCCESS(f'✅ {job_name} completed successfully')
                )
                success_count += 1
                
            except Exception as e:
                error_message = f'❌ {job_name} failed: {str(e)}'
                self.stdout.write(self.style.ERROR(error_message))
                logger.error(error_message, exc_info=True)
                error_count += 1
        
        # Summary
        total_jobs = len(cron_jobs)
        self.stdout.write(
            self.style.SUCCESS(
                f'\nCron jobs execution completed:\n'
                f'  - Total jobs: {total_jobs}\n'
                f'  - Successful: {success_count}\n'
                f'  - Failed: {error_count}\n'
                f'  - Completed at: {timezone.now()}'
            )
        )
        
        if error_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  {error_count} job(s) failed. Check the logs for details.'
                )
            )
