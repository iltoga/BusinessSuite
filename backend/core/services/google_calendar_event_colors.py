from django.conf import settings
from rest_framework.exceptions import ValidationError


class GoogleCalendarEventColors:
    """Centralized color and status mapping for Google Calendar events."""

    VALID_COLOR_IDS = {str(i) for i in range(1, 12)}

    @classmethod
    def validate_color_id(cls, color_id, *, field_name="color_id"):
        if color_id in (None, ""):
            raise ValidationError({field_name: "A color id is required."})

        normalized = str(color_id).strip()
        if normalized not in cls.VALID_COLOR_IDS:
            raise ValidationError({field_name: f"Invalid color id '{color_id}'. Expected one of 1-11."})
        return normalized

    @classmethod
    def todo_color_id(cls):
        configured = getattr(settings, "GOOGLE_CALENDAR_TODO_COLOR_ID", "5")
        return cls.validate_color_id(configured, field_name="GOOGLE_CALENDAR_TODO_COLOR_ID")

    @classmethod
    def done_color_id(cls):
        configured = getattr(settings, "GOOGLE_CALENDAR_DONE_COLOR_ID", "10")
        return cls.validate_color_id(configured, field_name="GOOGLE_CALENDAR_DONE_COLOR_ID")

    @classmethod
    def visa_window_color_id(cls):
        configured = getattr(settings, "GOOGLE_CALENDAR_VISA_WINDOW_COLOR_ID", "6")
        return cls.validate_color_id(configured, field_name="GOOGLE_CALENDAR_VISA_WINDOW_COLOR_ID")

    @classmethod
    def color_for_done_state(cls, done: bool):
        return cls.done_color_id() if done else cls.todo_color_id()

    @classmethod
    def is_done_color(cls, color_id):
        if not color_id:
            return False
        return str(color_id) == cls.done_color_id()
