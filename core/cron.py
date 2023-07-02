import datetime

# logging
import logging

from django.conf import settings
from django.core.management import call_command
from django_cron import CronJobBase, Schedule

logger = logging.getLogger(__name__)


class FullBackupJob(CronJobBase):
    schedule = Schedule(run_every_mins=settings.EVERY_ONE_DAY)
    code = "core.full_backup_job"

    def do(self):
        call_command("dbbackup")
        # log the backup
        logger.info("DB Backup created successfully")
        # Add the date to the directory name
        dir = "media_" + datetime.date.today().strftime("%Y%m%d")
        call_command("uploadmediatodropbox", dir)
        # log the upload
        logger.info("Media files uploaded successfully")


class ClearCacheJob(CronJobBase):
    schedule = Schedule(run_at_times=settings.CLEAR_CACHE_SCHEDULE)
    code = "core.clear_cache_job"

    def do(self):
        call_command("clear_cache")
        logger.info("Cache cleared successfully")
