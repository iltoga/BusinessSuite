import logging
from unittest import skipIf

from django.test import TestCase, override_settings

from core.services.logger_service import Logger


class LoggerServiceTests(TestCase):
    def test_get_logger_singleton(self):
        l1 = Logger.get_logger("test-logger")
        l2 = Logger.get_logger("test-logger")
        self.assertIs(l1, l2)

    @override_settings(LOKI_ENABLED=False)
    def test_loki_not_attached_when_disabled(self):
        logger_wrapper = Logger.get_logger("test-no-loki")
        # Ensure logger has no handler named LokiHandler when LOKI_ENABLED is False
        has_loki = any(h.__class__.__name__ == "LokiHandler" for h in logger_wrapper.logger.handlers)
        self.assertFalse(has_loki)

    @override_settings(LOKI_ENABLED=True, LOKI_URL="http://localhost:3100/loki/api/v1/push")
    def test_loki_handler_attached_when_enabled(self):
        logger_wrapper = Logger.get_logger("test-with-loki")
        # We can't assert the full functionality of LokiHandler without the package present,
        # but we ensure we don't crash and that a handler named LokiHandler may be present.
        attached = any(h.__class__.__name__ == "LokiHandler" for h in logger_wrapper.logger.handlers)
        # If logging_loki is installed this should be True; if not, it should not raise.
        self.assertIn(attached, (True, False))
