import logging
from unittest import skipIf

from django.test import TestCase, override_settings

from core.services.logger_service import Logger


class LoggerServiceTests(TestCase):
    def test_get_logger_singleton(self):
        l1 = Logger.get_logger("test-logger")
        l2 = Logger.get_logger("test-logger")
        self.assertIs(l1, l2)

    def test_file_handler_attached_and_writes(self):
        import os
        import tempfile

        # Use a temporary directory for logs
        tmpdir = tempfile.mkdtemp()
        with self.settings(LOG_DIR=tmpdir):
            logger_wrapper = Logger.get_logger("test-file-handler")
            # Ensure a file-based handler exists
            has_file = any(
                h.__class__.__name__ in ("ConcurrentRotatingFileHandler", "FileHandler")
                for h in logger_wrapper.logger.handlers
            )
            self.assertTrue(has_file)

            # Emit a message and ensure it is written to the expected log file
            logger_wrapper.info("hello-file")
            log_file = os.path.join(tmpdir, "test-file-handler.log")
            # Allow handler to flush
            for h in logger_wrapper.logger.handlers:
                try:
                    h.flush()
                except Exception:
                    pass

            self.assertTrue(os.path.exists(log_file), f"Expected log file at {log_file}")
            with open(log_file, "r", encoding="utf-8") as fh:
                contents = fh.read()
            self.assertIn("hello-file", contents)
