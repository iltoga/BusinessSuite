# Core models package — expose commonly imported models at package level.
# We use safe imports so that import-time issues (migrations/app registry) do not
# cause hard ImportErrors during early import phases.
try:
    from .country_code import CountryCode
except Exception:  # pragma: no cover - defensive import
    CountryCode = None

try:
    from .document_ocr_job import DocumentOCRJob
except Exception:  # pragma: no cover
    DocumentOCRJob = None

try:
    from .ocr_job import OCRJob
except Exception:  # pragma: no cover
    OCRJob = None

try:
    from .async_job import AsyncJob
except Exception:  # pragma: no cover
    AsyncJob = None

try:
    from .holiday import Holiday
except Exception:  # pragma: no cover
    Holiday = None

try:
    from .user_profile import UserProfile
except Exception:  # pragma: no cover
    UserProfile = None

try:
    from .user_settings import UserSettings
except Exception:  # pragma: no cover
    UserSettings = None

try:
    from .web_push_subscription import WebPushSubscription
except Exception:  # pragma: no cover
    WebPushSubscription = None

__all__ = [
    "CountryCode",
    "DocumentOCRJob",
    "OCRJob",
    "AsyncJob",
    "Holiday",
    "UserProfile",
    "UserSettings",
    "WebPushSubscription",
]
