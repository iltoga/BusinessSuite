import datetime
from unittest.mock import MagicMock, call, patch

import requests
from django.core.cache import cache
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


class OpenRouterHealthCheckTests(TestCase):
    @override_settings(
        OPENROUTER_HEALTHCHECK_ENABLED=True,
        OPENROUTER_API_KEY="test-key",
        OPENROUTER_API_BASE_URL="https://openrouter.ai/api/v1",
        OPENROUTER_HEALTHCHECK_TIMEOUT=7.0,
        OPENROUTER_HEALTHCHECK_MIN_CREDIT_REMAINING=0.0,
    )
    def test_health_check_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"limit_remaining": 123.45}}

        with patch("core.tasks.cron_jobs.requests.get", return_value=mock_response) as mock_get:
            result = cron_jobs._perform_openrouter_health_check()

        self.assertTrue(result)
        mock_get.assert_called_once_with(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": "Bearer test-key", "Accept": "application/json"},
            timeout=7.0,
        )

    @override_settings(OPENROUTER_HEALTHCHECK_ENABLED=False)
    def test_health_check_skipped_when_disabled(self):
        with patch("core.tasks.cron_jobs.requests.get") as mock_get:
            result = cron_jobs._perform_openrouter_health_check()

        self.assertTrue(result)
        mock_get.assert_not_called()

    @override_settings(
        OPENROUTER_HEALTHCHECK_ENABLED=True,
        OPENROUTER_API_KEY="test-key",
        OPENROUTER_API_BASE_URL="https://openrouter.ai/api/v1",
    )
    def test_health_check_http_failure(self):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("core.tasks.cron_jobs.requests.get", return_value=mock_response):
            result = cron_jobs._perform_openrouter_health_check()

        self.assertFalse(result)

    @override_settings(
        OPENROUTER_HEALTHCHECK_ENABLED=True,
        OPENROUTER_API_KEY="test-key",
        OPENROUTER_API_BASE_URL="https://openrouter.ai/api/v1",
    )
    def test_health_check_request_exception(self):
        with patch("core.tasks.cron_jobs.requests.get", side_effect=requests.RequestException("network down")):
            result = cron_jobs._perform_openrouter_health_check()

        self.assertFalse(result)

    @override_settings(
        OPENROUTER_HEALTHCHECK_ENABLED=True,
        OPENROUTER_API_KEY="test-key",
        OPENROUTER_API_BASE_URL="https://openrouter.ai/api/v1",
        OPENROUTER_HEALTHCHECK_MIN_CREDIT_REMAINING=1.0,
    )
    def test_health_check_low_credit_logs_error_and_fails(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"limit_remaining": 0.5}}

        with (
            patch("core.tasks.cron_jobs.requests.get", return_value=mock_response),
            patch("core.tasks.cron_jobs.logger.error") as mock_error,
        ):
            result = cron_jobs._perform_openrouter_health_check()

        self.assertFalse(result)
        self.assertTrue(
            any("low credit remaining" in str(call.args[0]) for call in mock_error.call_args_list),
            "Expected low-credit error log to be emitted",
        )

    @override_settings(
        OPENROUTER_HEALTHCHECK_ENABLED=True,
        OPENROUTER_API_KEY="test-key",
        OPENROUTER_API_BASE_URL="https://openrouter.ai/api/v1",
    )
    def test_health_check_invalid_limit_remaining_fails(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"limit_remaining": "not-a-number"}}

        with patch("core.tasks.cron_jobs.requests.get", return_value=mock_response):
            result = cron_jobs._perform_openrouter_health_check()

        self.assertFalse(result)

    @override_settings(
        OPENROUTER_HEALTHCHECK_ENABLED=True,
        OPENROUTER_API_KEY="test-key",
        OPENROUTER_API_BASE_URL="https://openrouter.ai/api/v1",
    )
    def test_health_check_missing_limit_remaining_fails(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"usage_monthly": 10}}

        with patch("core.tasks.cron_jobs.requests.get", return_value=mock_response):
            result = cron_jobs._perform_openrouter_health_check()

        self.assertFalse(result)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class PrivilegedCronTaskLockingTests(TestCase):
    def setUp(self):
        cron_jobs.reset_privileged_cron_job_locks()
        cache.clear()

    def tearDown(self):
        cron_jobs.reset_privileged_cron_job_locks()
        cache.clear()

    @patch("core.tasks.cron_jobs.run_full_backup_now")
    def test_enqueue_full_backup_is_idempotent_while_locked(self, backup_task_mock):
        first = cron_jobs.enqueue_full_backup_now()
        second = cron_jobs.enqueue_full_backup_now()

        self.assertTrue(first)
        self.assertFalse(second)
        backup_task_mock.delay.assert_called_once()

    @patch("core.tasks.cron_jobs._perform_clear_cache")
    def test_clear_cache_execution_skips_when_run_lock_exists(self, perform_clear_cache_mock):
        cache.set(cron_jobs.CLEAR_CACHE_RUN_LOCK_KEY, "other-run", timeout=300)

        executed = cron_jobs._perform_clear_cache_locked()

        self.assertFalse(executed)
        perform_clear_cache_mock.assert_not_called()

    @patch("core.tasks.cron_jobs.call_command")
    def test_full_backup_calls_dbbackup_and_uploadmediatos3(self, mock_call_command):
        cron_jobs._perform_full_backup()

        expected_dir_name = "media_" + datetime.date.today().strftime("%Y%m%d")
        self.assertEqual(
            mock_call_command.call_args_list,
            [call("dbbackup"), call("uploadmediatos3", expected_dir_name)],
        )

    @patch("core.tasks.cron_jobs._perform_full_backup")
    def test_full_backup_execution_releases_enqueue_lock_after_run(self, perform_full_backup_mock):
        cache.set(cron_jobs.FULL_BACKUP_ENQUEUE_LOCK_KEY, "queued-token", timeout=300)

        executed = cron_jobs._perform_full_backup_locked()

        self.assertTrue(executed)
        perform_full_backup_mock.assert_called_once()
        self.assertIsNone(cache.get(cron_jobs.FULL_BACKUP_ENQUEUE_LOCK_KEY))
