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

try:
    from .calendar_event import CalendarEvent
except Exception:  # pragma: no cover
    CalendarEvent = None

try:
    from .calendar_reminder import CalendarReminder
except Exception:  # pragma: no cover
    CalendarReminder = None

try:
    from .ai_request_usage import AIRequestUsage
except Exception:  # pragma: no cover
    AIRequestUsage = None

try:
    from .local_resilience import (
        LocalResilienceSettings,
        MediaManifestEntry,
        SyncChangeLog,
        SyncConflict,
        SyncCursor,
    )
except Exception:  # pragma: no cover
    LocalResilienceSettings = None
    SyncChangeLog = None
    SyncCursor = None
    SyncConflict = None
    MediaManifestEntry = None

__all__ = [
    "CountryCode",
    "DocumentOCRJob",
    "OCRJob",
    "AsyncJob",
    "Holiday",
    "UserProfile",
    "UserSettings",
    "WebPushSubscription",
    "CalendarEvent",
    "CalendarReminder",
    "AIRequestUsage",
    "LocalResilienceSettings",
    "SyncChangeLog",
    "SyncCursor",
    "SyncConflict",
    "MediaManifestEntry",
]
