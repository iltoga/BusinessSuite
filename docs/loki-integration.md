# Loki integration (DEPRECATED)

**Status:** Direct Loki emission has been removed from the codebase. We now rely on Grafana Alloy to collect logs from Docker container stdout/stderr and from files exposed to Alloy. This document is retained for historical reference only.

---

## Deprecation note

This document used to describe how to wire `logging_loki` to send logs directly to Loki. That approach has been removed from the codebase in favor of using Grafana Alloy to scrape Docker container logs and files.

Key guidance:

- Ensure Django writes its logs to `logs/` (the built-in `Logger` places per-module logs under `logs/` by default).
- Audit events are written as JSON lines to `logs/audit.log` by `core.audit_handlers.PersistentLokiBackend` (kept for compatibility).
- Configure Grafana Alloy (see `howtos/GRAFANA_CLOUD_SETUP.md`) to scrape Docker container stdout/stderr and any log files you choose to expose.

If you still need direct push to Loki, consider reintroducing a tailored integration and update this document accordingly.

## Components & packages 🔧

- Loki service: `loki` (configured via `loki-config.yaml` and `docker-compose.yml`) ✅
- Grafana (optional) for exploring logs
- Python package: `python-logging-loki` (already present in `pyproject.toml` as `python-logging-loki>=0.3.0`)

## Docker Compose (Loki) example

In this repo Loki is run as a container in `docker-compose.yml` and `docker-compose_local.yml`. Key parts:

```yaml
# docker-compose.yml (excerpt)
bs-loki:
  container_name: bs-loki
  image: grafana/loki:3.5.1
  restart: unless-stopped
  ports:
    - "3100:3100"
  volumes:
    - loki-data:/loki
    - ./grafana/loki-config.yaml:/etc/loki/local-config.yaml:ro
  command: -config.file=/etc/loki/local-config.yaml
  networks:
    - dockernet
```

`./grafana/loki-config.yaml` in the repo configures storage, retention and server port (default 3100).

---

## Environment variables used

- `LOKI_ENABLED` (true/false) — enable sending logs to Loki
- `LOKI_URL` — endpoint where Loki accepts pushes (example: `http://bs-loki:3100/loki/api/v1/push`)
- `LOKI_APPLICATION` — tag value for `application`
- `LOKI_JOB` — tag value for `job` (typically the service name)

These env variables are supplied to containers in `docker-compose.yml`. each container has different job and loki_application (examples):

```yaml
environment:
  LOKI_ENABLED: "true"
  LOKI_URL: "http://bs-loki:3100/loki/api/v1/push"
  LOKI_JOB: "backend" # or "frontend" or "worker"
  LOKI_APPLICATION: "bs-core" # or "bs-frontend" or "bs-worker"
```

---

## Django settings (dict-based logging)

This repo configures `LOKI_*` in `business_suite.settings.base`. When `LOKI_ENABLED` is true the repo appends a `loki` handler to `LOGGING` programmatically. Key snippet:

```python
LOKI_ENABLED = os.getenv("LOKI_ENABLED", "False").lower() == "true"
LOKI_URL = os.getenv("LOKI_URL", "http://bs-loki:3100/loki/api/v1/push")
LOKI_JOB = os.getenv("LOKI_JOB", "django")
LOKI_APPLICATION = os.getenv("LOKI_APPLICATION", "business_suite")

if LOKI_ENABLED:
    LOGGING["handlers"]["loki"] = {
        "level": LOGGING_LEVEL,
        "class": "logging_loki.LokiHandler",
        "url": LOKI_URL,
        "tags": {"application": LOKI_APPLICATION, "job": LOKI_JOB},
        "version": "1",
    }
    for logger_name in ["business_suite", "worker", "frontend"]:
        if logger_name in LOGGING["loggers"]:
            LOGGING["loggers"][logger_name]["handlers"].append("loki")
```

This approach lets Django’s logging framework send logs to Loki by adding `logging_loki.LokiHandler` as a handler in the `LOGGING` dict.

---

## Programmatic integration (central Logger service)

The repository also provides a centralized `Logger` in `core/services/logger_service.py` that:

- Creates file + console handlers
- Optionally attaches a `LokiHandler` when `settings.LOKI_ENABLED` is true
- Prevents duplicate handlers using `isinstance` checks
- Adds a small filter to exclude noisy request logs

Core snippet:

```python
from logging_loki import LokiHandler

# ... inside Logger._create_logger(name)
if getattr(settings, "LOKI_ENABLED", False) and not any(isinstance(h, LokiHandler) for h in logger.handlers):
    loki_url = getattr(settings, "LOKI_URL", "http://bs-loki:3100/loki/api/v1/push")
    loki_application = getattr(settings, "LOKI_APPLICATION", "business_suite")
    loki_job = getattr(settings, "LOKI_JOB", name)

    loki_handler = LokiHandler(
        url=loki_url, tags={"application": loki_application, "job": loki_job}, version="1"
    )
    loki_handler.setLevel(logging.DEBUG)
    loki_handler.setFormatter(formatter)
    logger.addHandler(loki_handler)
```

Notes:

- The `tags` map is important: use `application` and `job` (or any tags you prefer) so logs can be filtered in Grafana/Loki.
- The code checks for existing `LokiHandler` instances to avoid duplicate events.

### Full Logger implementation (copy/paste)

Below is the complete `Logger` used in this repository (`core/services/logger_service.py`). It centralizes logger creation (console, rotating file) and conditionally attaches a `LokiHandler` when `LOKI_ENABLED` is set. Copy it into your project and adapt paths/tags as needed.

```python
import logging
import os
import threading
import time

from concurrent_log_handler import ConcurrentRotatingFileHandler
from django.conf import settings
from logging_loki import LokiHandler


class NoHttpRequestFilter(logging.Filter):
    def filter(self, record):
        # Exclude logs that contain "HTTP Request:"
        return "HTTP Request:" not in record.getMessage()


class Logger:
    _instances = {}
    _lock = threading.Lock()  # Thread safety

    def __init__(self, logger: logging.Logger) -> None:
        self.logging_level = settings.LOGGING_LEVEL
        self.loki_enabled = settings.LOKI_ENABLED

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

        logging_level = settings.LOGGING_LEVEL or "INFO"
        log_dir = "./logs"
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
        if getattr(settings, "LOKI_ENABLED", False) and not any(isinstance(h, LokiHandler) for h in logger.handlers):
            loki_url = getattr(settings, "LOKI_URL", "http://loki:3100/loki/api/v1/push")
            loki_application = getattr(settings, "LOKI_APPLICATION", "business_suite")
            loki_job = getattr(settings, "LOKI_JOB", name)

            loki_handler = LokiHandler(
                url=loki_url, tags={"application": loki_application, "job": loki_job}, version="1"
            )
            loki_handler.setLevel(logging.DEBUG)
            loki_handler.setFormatter(formatter)
            logger.addHandler(loki_handler)

        return logger
```

Notes on the implementation:

- Uses `ConcurrentRotatingFileHandler` to safely rotate logs across processes (good for containers/uwsgi/celery workers).
- Provides `get_logger(name)` to return a singleton per logger name.
- Add or modify filters to redact PII or very large payloads before logs reach Loki.

### Minimal usage example

```python
# any module, e.g. app/tasks.py or app/views.py
from core.services.logger_service import Logger

# Get a singleton logger for this module or component
logger = Logger.get_logger("myapp")  # or Logger.get_logger(__name__)

logger.info("Starting background job")
try:
    result = 1 / 0
except Exception:
    logger.exception("Job failed")
```

> Tip: prefer `Logger.get_logger(__name__)` for module-scoped loggers to make filtering by module easier in Grafana.

---

## Request logging middleware example

A small middleware logs incoming requests and responses via the central `Logger`:

```python
# core/middleware/log_request_middleware.py
from core.services.logger_service import Logger

class LogRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = Logger.get_logger()

    def __call__(self, request):
        self.logger.info(f"Request Method: {request.method}")
        self.logger.info(f"Request Path: {request.path}")
        self.logger.info(f"Request Headers: {dict(request.headers)}")
        # ... log request body and response info ...
        return self.get_response(request)
```

> Tip: middleware-based request logging will send HTTP data to Loki via the `LokiHandler` attached to the same logger. Use filters to avoid logging sensitive data or enormous request bodies.

---

## Small test script for pushing logs to Loki

There is a test helper `test_loki_push.py` to manually verify connectivity:

```python
import logging
import logging_loki

handler = logging_loki.LokiHandler(
    url="http://localhost:3100/loki/api/v1/push",
    tags={"application": "test-app", "job": "test-job"},
    version="1",
)
logger = logging.getLogger("loki-test")
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.info("This is a test log message from the host machine to Loki.")
```

Run with: `python test_loki_push.py` (or execute in a quick script) and check the Grafana Explore UI for `job="test-job"`.

---

## Best practices & checklist ✅

- Add `python-logging-loki` to your dependencies.
- Add a `loki` service to your local `docker-compose.yml` and bind `loki-config.yaml`.
- Expose `LOKI_*` environment variables for each service (`LOKI_URL`, `LOKI_ENABLED`, `LOKI_APPLICATION`, `LOKI_JOB`).
- Choose one integration mode:
  - Dict-based: add a `loki` handler in Django’s `LOGGING` (good for global Django loggers), or
  - Programmatic: attach `LokiHandler` where you construct loggers (useful for app-specific singletons and fine control).
- Avoid logging sensitive data; add filters to strip or redact PII and large payloads (see `NoHttpRequestFilter` pattern in repo).
- Test connectivity with a small script before relying on production logs.
- Use distinct tags (`application`, `job`, `environment`) to make queries easy in Grafana.

---

## Template checklist (copy into new project)

1. Add dependency to `pyproject.toml` / `requirements.txt`:
   - `python-logging-loki>=0.3.0`
2. Add Loki & Grafana to `docker-compose.yml` (use this repo’s `loki-config.yaml` as a start).
3. Add env variables to service definitions: `LOKI_ENABLED`, `LOKI_URL`, `LOKI_APPLICATION`, `LOKI_JOB`.
4. In Django settings:
   - Define `LOKI_ENABLED`, `LOKI_URL`, `LOKI_APPLICATION`, `LOKI_JOB`.
   - Either append a `loki` handler to `LOGGING` or programmatically attach `LokiHandler` in your logger factory.
5. Add a small test script to verify push.
6. Add filters/middleware to avoid noisy or sensitive logs.

---

## References in this repository (for copy/paste)

- `business_suite/settings/base.py` — settings and `LOGGING` conditional handler
- `core/services/logger_service.py` — programmatic `LokiHandler` integration and helper `Logger` class
- `core/middleware/log_request_middleware.py` — example request logging middleware
- `test_loki_push.py` — simple push test script
- `docker-compose.yml` and `docker-compose_local.yml` — how to wire environment variables and run Loki
- `grafana/loki-config.yaml` — Loki configuration (retention, ports, filesystem storage)
