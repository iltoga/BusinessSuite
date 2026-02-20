from __future__ import annotations

from core.models import CalendarEvent, CalendarReminder
from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class _CalendarReminderBaseWriteSerializer(serializers.Serializer):
    reminder_date = serializers.DateField()
    reminder_time = serializers.TimeField(input_formats=["%H:%M", "%H:%M:%S"])
    timezone = serializers.CharField(max_length=64, default=CalendarReminder.DEFAULT_TIMEZONE)
    content = serializers.CharField(max_length=2000)
    calendar_event_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_content(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Content cannot be empty.")
        return cleaned

    def validate(self, attrs):
        instance = getattr(self, "instance", None)

        timezone_value = attrs.get("timezone")
        if timezone_value is None:
            timezone_name = getattr(instance, "timezone", CalendarReminder.DEFAULT_TIMEZONE)
        else:
            timezone_name = timezone_value.strip() or CalendarReminder.DEFAULT_TIMEZONE
            attrs["timezone"] = timezone_name

        reminder_date = attrs.get("reminder_date") or getattr(instance, "reminder_date", None)
        reminder_time = attrs.get("reminder_time") or getattr(instance, "reminder_time", None)

        if reminder_date is None or reminder_time is None:
            raise serializers.ValidationError("Both reminderDate and reminderTime are required.")

        CalendarReminder.compute_scheduled_for(
            reminder_date=reminder_date,
            reminder_time=reminder_time,
            timezone_name=timezone_name,
        )

        marker = object()
        calendar_event_id = attrs.get("calendar_event_id", marker)
        if calendar_event_id is marker:
            return attrs

        if calendar_event_id:
            if not CalendarEvent.objects.filter(pk=calendar_event_id).exists():
                raise serializers.ValidationError({"calendarEventId": "Calendar event not found."})
        else:
            attrs["calendar_event_id"] = None
        return attrs


class CalendarReminderCreateSerializer(_CalendarReminderBaseWriteSerializer):
    user_id = serializers.IntegerField(required=False, min_value=1)

    def validate_user_id(self, value: int) -> int:
        if not User.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("User not found or inactive.")
        return value


class CalendarReminderBulkCreateSerializer(_CalendarReminderBaseWriteSerializer):
    user_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def validate_user_ids(self, values: list[int]) -> list[int]:
        unique_values = []
        for value in values:
            if value not in unique_values:
                unique_values.append(value)

        existing = set(User.objects.filter(id__in=unique_values, is_active=True).values_list("id", flat=True))
        missing = [value for value in unique_values if value not in existing]
        if missing:
            raise serializers.ValidationError(f"User(s) not found or inactive: {missing}")
        return unique_values


class CalendarReminderInboxMarkReadSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )
    device_label = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class CalendarReminderSerializer(serializers.ModelSerializer):
    user_full_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    created_by_full_name = serializers.SerializerMethodField()
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = CalendarReminder
        fields = [
            "id",
            "user",
            "user_full_name",
            "user_email",
            "created_by",
            "created_by_full_name",
            "created_by_email",
            "calendar_event",
            "reminder_date",
            "reminder_time",
            "timezone",
            "scheduled_for",
            "content",
            "status",
            "sent_at",
            "read_at",
            "delivery_channel",
            "delivery_device_label",
            "read_device_label",
            "error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "scheduled_for",
            "status",
            "sent_at",
            "read_at",
            "delivery_channel",
            "delivery_device_label",
            "read_device_label",
            "error_message",
            "created_at",
            "updated_at",
            "user_full_name",
            "user_email",
            "created_by_full_name",
            "created_by_email",
        ]

    def get_user_full_name(self, obj: CalendarReminder) -> str:
        return obj.user.get_full_name().strip() or obj.user.username

    def get_user_email(self, obj: CalendarReminder) -> str:
        return obj.user.email or ""

    def get_created_by_full_name(self, obj: CalendarReminder) -> str:
        if not obj.created_by:
            return ""
        return obj.created_by.get_full_name().strip() or obj.created_by.username

    def get_created_by_email(self, obj: CalendarReminder) -> str:
        if not obj.created_by:
            return ""
        return obj.created_by.email or ""
