import logging
import os
import threading
import time

from concurrent_log_handler import ConcurrentRotatingFileHandler
from django.conf import settings


class NoHttpRequestFilter(logging.Filter):
    def filter(self, record):
        # Exclude logs that contain "HTTP Request:"
        return "HTTP Request:" not in record.getMessage()


class Logger:
    _instances = {}
    _lock = threading.Lock()  # Thread safety

    def __init__(self, logger: logging.Logger) -> None:
        self.logging_level = getattr(settings, "LOGGING_LEVEL", "INFO")
        self.loki_enabled = getattr(settings, "LOKI_ENABLED", False)

        self.logger = logger

    def __getattr__(self, attr):
        # Delegate attribute access to the wrapped logger
        return getattr(self.logger, attr)

    def debug(self, msg, *args, sleep: float = None, **kwargs):
        result = self.logger.debug(msg, *args, **kwargs)
        if sleep is not None:
            time.sleep(sleep)
        return result

    def info(self, msg, *args, sleep: float = None, **kwargs):
        result = self.logger.info(msg, *args, **kwargs)
        if sleep is not None:
            time.sleep(sleep)
        return result

    def warning(self, msg, *args, sleep: float = None, **kwargs):
        result = self.logger.warning(msg, *args, **kwargs)
        if sleep is not None:
            time.sleep(sleep)
        return result

    def error(self, msg, *args, sleep: float = None, **kwargs):
        result = self.logger.error(msg, *args, **kwargs)
        if sleep is not None:
            time.sleep(sleep)
        return result

    def critical(self, msg, *args, sleep: float = None, **kwargs):
        result = self.logger.critical(msg, *args, **kwargs)
        if sleep is not None:
            time.sleep(sleep)
        return result

    def exception(self, msg, *args, sleep: float = None, exc_info=True, **kwargs):
        import sys

        current_exc_type, current_exc_val, _ = sys.exc_info()

        # Check if we should suppress traceback for TaskCancelledException
        if current_exc_type and current_exc_type.__name__ == "TaskCancelledException" and exc_info:
            exc_info = False
            # If msg is a string and does not contain the exception message, append it
            if isinstance(msg, str):
                exc_msg = str(current_exc_val)
                if exc_msg and exc_msg not in msg:
                    # If there are args, they need to be applied before appending
                    try:
                        if args:
                            msg = msg % args
                            args = ()
                    except Exception:  # pylint: disable=broad-except
                        pass
                    msg = f"{msg}. The error is: {exc_msg}"

        result = self.logger.exception(msg, *args, exc_info=exc_info, **kwargs)
        if sleep is not None:
            time.sleep(sleep)
        return result

    def log(self, level, msg, *args, sleep: float = None, **kwargs):
        result = self.logger.log(level, msg, *args, **kwargs)
        if sleep is not None:
            time.sleep(sleep)
        return result

    @classmethod
    def get_logger(cls, name: str = "app") -> "Logger":
        """
        Returns a singleton `Logger` instance for the provided name.
        """
        key = (name,)
        with cls._lock:
            if key not in cls._instances:
                logger = cls._create_logger(name)
                cls._instances[key] = Logger(logger)
            return cls._instances[key]

    @staticmethod
    def _create_logger(name: str) -> logging.Logger:
        logger = logging.getLogger(name)

        logging_level = getattr(settings, "LOGGING_LEVEL", "INFO")
        log_dir = getattr(settings, "LOG_DIR", "./logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file_name = f"{log_dir}/{name}.log"

        logger.setLevel(logging_level.upper())

        # Create formatter for log messages
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        # Create console handler and file handler
        if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
            console_handler = logging.StreamHandler()
            file_handler = ConcurrentRotatingFileHandler(log_file_name, "a", 1 * 1024 * 1024, 10)

            console_handler.setLevel(logging_level.upper())
            file_handler.setLevel(logging_level.upper())

            # Add formatter to the handlers
            console_handler.setFormatter(formatter)
            file_handler.setFormatter(formatter)

            # Exclude HTTP Request logs from being logged
            http_request_filter = NoHttpRequestFilter()
            console_handler.addFilter(http_request_filter)
            file_handler.addFilter(http_request_filter)

            # Add handlers to logger
            logger.addHandler(console_handler)
            logger.addHandler(file_handler)

        # Add Loki handler if enabled
        if getattr(settings, "LOKI_ENABLED", False) and not any(
            h.__class__.__name__ == "LokiHandler" for h in logger.handlers
        ):
            try:
                from logging_loki import LokiHandler

                loki_url = getattr(settings, "LOKI_URL", "http://loki:3100/loki/api/v1/push")
                loki_application = getattr(settings, "LOKI_APPLICATION", "business_suite")
                loki_job = getattr(settings, "LOKI_JOB", "backend") if not name else name

                loki_handler = LokiHandler(
                    url=loki_url, tags={"application": loki_application, "job": loki_job}, version="1"
                )
                loki_handler.setLevel(logging.DEBUG)
                loki_handler.setFormatter(formatter)
                logger.addHandler(loki_handler)
            except Exception:
                # Don't break if Loki is unavailable at import time
                pass

        return logger
