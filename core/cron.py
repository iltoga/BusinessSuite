import datetime

# logging
import logging

from django.conf import settings
from django.core.management import call_command

logger = logging.getLogger(__name__)


class BaseCronJob:
    """Base class for cron jobs to replace django_cron.CronJobBase"""
    def __init__(self):
        pass
    
    def do(self):
        """Override this method in subclasses"""
        raise NotImplementedError("Subclasses must implement the do() method")


class FullBackupJob(BaseCronJob):
    """Full backup job - runs every day"""
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


class ClearCacheJob(BaseCronJob):
    """Clear cache job - runs at scheduled times"""
    code = "core.clear_cache_job"

    def do(self):
        call_command("clear_cache")
        logger.info("Cache cleared successfully")
