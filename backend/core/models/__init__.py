"""Core model exports.

Expose model classes at package level for imports like `from core.models import X`.
Use explicit imports so import errors are not silently converted to `None`.
"""

from .ai_model import AiModel
from .ai_request_usage import AIRequestUsage
from .app_setting import AppSetting
from .async_job import AsyncJob
from .calendar_event import CalendarEvent
from .calendar_reminder import CalendarReminder
from .country_code import CountryCode
from .document_ocr_job import DocumentOCRJob
from .holiday import Holiday
from .local_resilience import LocalResilienceSettings, MediaManifestEntry, SyncChangeLog, SyncConflict, SyncCursor
from .ocr_job import OCRJob
from .ui_settings import UiSettings
from .user_profile import UserProfile
from .user_settings import UserSettings
from .web_push_subscription import WebPushSubscription

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
    "AiModel",
    "AIRequestUsage",
    "LocalResilienceSettings",
    "SyncChangeLog",
    "SyncCursor",
    "SyncConflict",
    "MediaManifestEntry",
    "UiSettings",
    "AppSetting",
]
