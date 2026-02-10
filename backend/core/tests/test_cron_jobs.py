import datetime
from unittest.mock import patch

from django.test import TestCase, override_settings

from core.tasks import cron_jobs


class AuditLogPruneTests(TestCase):
    @override_settings(AUDITLOG_RETENTION_DAYS=14)
    def test_prune_calls_auditlogflush_with_expected_date(self):
        expected_cutoff = datetime.date.today() - datetime.timedelta(days=14)
        with patch("core.tasks.cron_jobs.call_command") as mock_call:
            cron_jobs._perform_prune_auditlog()
            mock_call.assert_called_once()
            # first arg should be the management command name
            args, kwargs = mock_call.call_args
            assert args[0] == "auditlogflush"
            assert kwargs.get("before_date") == expected_cutoff.isoformat()
            assert kwargs.get("yes") is True

    @override_settings(AUDITLOG_RETENTION_DAYS=0)
    def test_prune_skipped_when_retention_nonpositive(self):
        with patch("core.tasks.cron_jobs.call_command") as mock_call:
            cron_jobs._perform_prune_auditlog()
            mock_call.assert_not_called()
