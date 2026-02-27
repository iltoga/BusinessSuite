import logging
import uuid
from datetime import datetime, time, timedelta
from typing import Iterable

from core.models.calendar_event import CalendarEvent
from core.services.google_calendar_event_colors import GoogleCalendarEventColors
from customer_applications.models import WorkflowNotification
from customer_applications.services.stay_permit_submission_window_service import StayPermitSubmissionWindowService
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class ApplicationCalendarService:
    PRIVATE_PROP_ENTITY_KEY = "revisbali_entity"
    PRIVATE_PROP_APPLICATION_ID_KEY = "revisbali_customer_application_id"
    PRIVATE_PROP_TASK_ID_KEY = "revisbali_task_id"
    PRIVATE_PROP_TASK_STEP_KEY = "revisbali_task_step"
    PRIVATE_PROP_EVENT_KIND_KEY = "revisbali_event_kind"
    PRIVATE_PROP_ENTITY_VALUE = "customer_application"
    EVENT_KIND_TASK_DEADLINE = "task_deadline"
    EVENT_KIND_VISA_SUBMISSION_WINDOW = "visa_submission_window"

    def sync_next_task_deadline(self, application, start_date=None, previous_due_date=None):
        if not application.add_deadlines_to_calendar:
            self.delete_application_events(application, clear_application_reference=True)
            return None

        task = application.get_next_calendar_task()
        if not task:
            if application.calendar_event_id:
                application.calendar_event_id = None
                application.save(update_fields=["calendar_event_id", "updated_at"])
            self._sync_visa_submission_window_event(application)
            return None

        if start_date:
            due_date = application.calculate_next_calendar_due_date(start_date=start_date)
        else:
            due_date = application.due_date or application.calculate_next_calendar_due_date(
                start_date=application.doc_date
            )

        current_event = self._get_existing_calendar_event_for_application(application)
        current_event_task_id, _ = self._event_task_identity(current_event)
        if (
            previous_due_date is not None
            and previous_due_date == due_date
            and current_event
            and current_event_task_id == task.id
        ):
            logger.debug(
                "calendar_mirror_noop_same_due_date application_id=%s task_id=%s event_id=%s",
                application.id,
                task.id,
                current_event.id,
            )
            self._sync_visa_submission_window_event(application)
            return current_event

        if application.due_date != due_date:
            application.due_date = due_date
            application.save(update_fields=["due_date", "updated_at"])

        event_payload = self._build_calendar_event_payload(application, task, due_date)
        try:
            event = self._upsert_calendar_event(
                application=application,
                task=task,
                due_date=due_date,
                payload=event_payload,
            )
        except Exception as exc:
            logger.error(
                "calendar_mirror_upsert_failed application_id=%s error_type=%s error=%s payload=%s",
                application.id,
                type(exc).__name__,
                str(exc),
                event_payload,
            )
            self._sync_visa_submission_window_event(application)
            return None

        if event and event.id and application.calendar_event_id != event.id:
            application.calendar_event_id = event.id
            application.save(update_fields=["calendar_event_id", "updated_at"])
        elif not event and application.calendar_event_id:
            application.calendar_event_id = None
            application.save(update_fields=["calendar_event_id", "updated_at"])

        self._sync_visa_submission_window_event(application)
        return event

    def delete_application_events(self, application, clear_application_reference=True):
        known_event_ids = self._known_event_ids_from_application(application)
        deleted_count = self.delete_events_for_application_id(
            application_id=application.id,
            known_event_ids=known_event_ids,
        )

        if clear_application_reference and application.calendar_event_id:
            application.calendar_event_id = None
            application.save(update_fields=["calendar_event_id", "updated_at"])

        return deleted_count

    def delete_events_for_application_id(self, application_id: int, known_event_ids: Iterable[str] | None = None):
        known_ids = set(filter(None, known_event_ids or []))
        query = Q(application_id=application_id)
        if known_ids:
            query |= Q(id__in=known_ids) | Q(google_event_id__in=known_ids)

        events = list(CalendarEvent.objects.filter(query).distinct())
        logger.debug(
            "calendar_local_delete_many_start application_id=%s matched_events=%s known_ids=%s",
            application_id,
            len(events),
            sorted(known_ids),
        )
        for event in events:
            logger.debug(
                "calendar_local_delete event_id=%s application_id=%s google_event_id=%s",
                event.id,
                event.application_id,
                event.google_event_id,
            )
            event.delete()
        return len(events)

    def _known_event_ids_from_application(self, application):
        event_ids = set()
        if application.calendar_event_id:
            event_ids.add(application.calendar_event_id)

        notification_refs = (
            WorkflowNotification.objects.filter(
                doc_application=application,
                notification_type="",
                external_reference__isnull=False,
            )
            .exclude(external_reference="")
            .values_list("external_reference", flat=True)
        )
        event_ids.update(notification_refs)
        return event_ids

    def _build_calendar_event_payload(self, application, task, due_date):
        notify_days = task.notify_days_before or 0
        reminder_minutes = max(0, notify_days * 24 * 60)

        notes = application.notes or "-"
        description = (
            f"Application #{application.id}\n"
            f"Customer: {application.customer.full_name}\n"
            f"Product: {application.product.name}\n"
            f"Task: {task.name}\n"
            f"Application Notes: {notes}"
        )

        return {
            "summary": f"[Application #{application.id}] {application.customer.full_name} - {task.name}",
            "description": description,
            "start_date": due_date.isoformat(),
            "end_date": (due_date + timedelta(days=1)).isoformat(),
            "color_id": GoogleCalendarEventColors.todo_color_id(),
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": reminder_minutes}]},
            "extended_properties": {"private": self._private_properties(application, task, self.EVENT_KIND_TASK_DEADLINE)},
        }

    def _upsert_calendar_event(self, *, application, task, due_date, payload):
        event = self._get_existing_calendar_event_for_application(application)
        target_task_id = task.id
        target_task_step = task.step

        if event:
            event_task_id, event_task_step = self._event_task_identity(event)
            if event_task_id and event_task_id != target_task_id:
                is_rollback = event_task_step is not None and event_task_step > target_task_step
                if is_rollback:
                    logger.debug(
                        "calendar_local_delete_rolled_back_task application_id=%s old_event_id=%s old_task_id=%s new_task_id=%s",
                        application.id,
                        event.id,
                        event_task_id,
                        target_task_id,
                    )
                    event.delete()
                    event = self._get_latest_event_for_task(application=application, task_id=target_task_id)
                else:
                    event = None

        if event is None:
            event = self._get_latest_event_for_task(application=application, task_id=target_task_id)

        event_values = {
            "title": payload["summary"],
            "description": payload.get("description", ""),
            "start_date": due_date,
            "end_date": due_date + timedelta(days=1),
            "color_id": payload.get("color_id"),
            "notifications": payload.get("reminders") or {},
            "extended_properties": payload.get("extended_properties") or {},
        }

        if event:
            update_fields = []
            for field_name, value in event_values.items():
                if getattr(event, field_name) != value:
                    setattr(event, field_name, value)
                    update_fields.append(field_name)

            if event.sync_status != CalendarEvent.SYNC_STATUS_PENDING:
                event.sync_status = CalendarEvent.SYNC_STATUS_PENDING
                update_fields.append("sync_status")

            if event.sync_error:
                event.sync_error = ""
                update_fields.append("sync_error")

            if update_fields:
                logger.debug(
                    "calendar_local_update event_id=%s application_id=%s task_id=%s fields=%s",
                    event.id,
                    application.id,
                    target_task_id,
                    sorted(update_fields),
                )
                event.save(update_fields=[*update_fields, "updated_at"])
            return event

        new_event_id = self._build_local_event_id(application.id)
        logger.debug(
            "calendar_local_create event_id=%s application_id=%s task_id=%s due_date=%s",
            new_event_id,
            application.id,
            target_task_id,
            due_date,
        )
        return CalendarEvent.objects.create(
            id=new_event_id,
            source=CalendarEvent.SOURCE_APPLICATION,
            application=application,
            sync_status=CalendarEvent.SYNC_STATUS_PENDING,
            **event_values,
        )

    def _get_existing_calendar_event_for_application(self, application):
        if application.calendar_event_id:
            event = CalendarEvent.objects.filter(pk=application.calendar_event_id).first()
            if event and not self._is_visa_submission_window_event(event):
                return event

        return (
            CalendarEvent.objects.filter(
                application=application,
                source=CalendarEvent.SOURCE_APPLICATION,
            )
            .exclude(
                extended_properties__private__revisbali_event_kind=self.EVENT_KIND_VISA_SUBMISSION_WINDOW
            )
            .order_by("-updated_at", "-created_at")
            .first()
        )

    def _build_local_event_id(self, application_id: int) -> str:
        return f"local-app-{application_id}-{uuid.uuid4().hex[:12]}"

    def _private_properties(self, application, task, event_kind: str):
        private_props = {
            self.PRIVATE_PROP_ENTITY_KEY: self.PRIVATE_PROP_ENTITY_VALUE,
            self.PRIVATE_PROP_APPLICATION_ID_KEY: str(application.id),
            self.PRIVATE_PROP_EVENT_KIND_KEY: event_kind,
        }
        if task is not None:
            private_props[self.PRIVATE_PROP_TASK_ID_KEY] = str(task.id)
            private_props[self.PRIVATE_PROP_TASK_STEP_KEY] = str(task.step)
        return private_props

    def _event_task_identity(self, event):
        if not event:
            return (None, None)

        private_props = (event.extended_properties or {}).get("private") or {}
        task_id_raw = private_props.get(self.PRIVATE_PROP_TASK_ID_KEY)
        task_step_raw = private_props.get(self.PRIVATE_PROP_TASK_STEP_KEY)

        try:
            task_id = int(task_id_raw) if task_id_raw is not None else None
        except (TypeError, ValueError):
            task_id = None

        try:
            task_step = int(task_step_raw) if task_step_raw is not None else None
        except (TypeError, ValueError):
            task_step = None

        return (task_id, task_step)

    def _get_latest_event_for_task(self, *, application, task_id: int):
        return (
            CalendarEvent.objects.filter(
                application=application,
                source=CalendarEvent.SOURCE_APPLICATION,
                extended_properties__private__revisbali_task_id=str(task_id),
            )
            .order_by("-updated_at", "-created_at")
            .first()
        )

    def _sync_visa_submission_window_event(self, application):
        try:
            window = StayPermitSubmissionWindowService().get_submission_window(
                product=application.product,
                application=application,
            )
            existing_event = self._get_visa_submission_window_event(application)
            if not window:
                if existing_event:
                    logger.debug(
                        "calendar_local_delete_visa_window_event application_id=%s event_id=%s",
                        application.id,
                        existing_event.id,
                    )
                    existing_event.delete()
                return None

            start_date = window.first_date
            end_date = window.last_date + timedelta(days=1)
            payload = self._build_visa_submission_window_payload(application, start_date=start_date, end_date=end_date)

            event_values = {
                "title": payload["summary"],
                "description": payload.get("description", ""),
                "start_date": start_date,
                "end_date": end_date,
                "color_id": payload.get("color_id"),
                "notifications": {},
                "extended_properties": payload.get("extended_properties") or {},
            }

            if existing_event:
                update_fields = []
                for field_name, value in event_values.items():
                    if getattr(existing_event, field_name) != value:
                        setattr(existing_event, field_name, value)
                        update_fields.append(field_name)

                if existing_event.sync_status != CalendarEvent.SYNC_STATUS_PENDING:
                    existing_event.sync_status = CalendarEvent.SYNC_STATUS_PENDING
                    update_fields.append("sync_status")

                if existing_event.sync_error:
                    existing_event.sync_error = ""
                    update_fields.append("sync_error")

                if update_fields:
                    logger.debug(
                        "calendar_local_update_visa_window_event application_id=%s event_id=%s fields=%s",
                        application.id,
                        existing_event.id,
                        sorted(update_fields),
                    )
                    existing_event.save(update_fields=[*update_fields, "updated_at"])
                return existing_event

            new_event_id = self._build_local_event_id(application.id)
            logger.debug(
                "calendar_local_create_visa_window_event application_id=%s event_id=%s start=%s end=%s",
                application.id,
                new_event_id,
                start_date,
                end_date,
            )
            return CalendarEvent.objects.create(
                id=new_event_id,
                source=CalendarEvent.SOURCE_APPLICATION,
                application=application,
                sync_status=CalendarEvent.SYNC_STATUS_PENDING,
                **event_values,
            )
        except Exception as exc:
            logger.exception(
                "calendar_mirror_visa_window_upsert_failed application_id=%s error_type=%s error=%s",
                application.id,
                type(exc).__name__,
                str(exc),
            )
            return None

    def _build_visa_submission_window_payload(self, application, *, start_date, end_date):
        window_end_inclusive = end_date - timedelta(days=1)
        description = (
            f"Application #{application.id}\n"
            f"Customer: {application.customer.full_name}\n"
            f"Product: {application.product.name}\n"
            f"Visa submission window: {start_date.isoformat()} to {window_end_inclusive.isoformat()} (inclusive)"
        )
        return {
            "summary": f"[Application #{application.id}] {application.customer.full_name} - Visa submission window",
            "description": description,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "color_id": GoogleCalendarEventColors.visa_window_color_id(),
            "extended_properties": {
                "private": self._private_properties(
                    application,
                    task=None,
                    event_kind=self.EVENT_KIND_VISA_SUBMISSION_WINDOW,
                )
            },
        }

    def _get_visa_submission_window_event(self, application):
        return (
            CalendarEvent.objects.filter(
                application=application,
                source=CalendarEvent.SOURCE_APPLICATION,
                extended_properties__private__revisbali_event_kind=self.EVENT_KIND_VISA_SUBMISSION_WINDOW,
            )
            .order_by("-updated_at", "-created_at")
            .first()
        )

    def _is_visa_submission_window_event(self, event):
        private_props = (event.extended_properties or {}).get("private") or {}
        return private_props.get(self.PRIVATE_PROP_EVENT_KIND_KEY) == self.EVENT_KIND_VISA_SUBMISSION_WINDOW

    def _create_notification(self, application, task, due_date, event, workflow=None):
        notify_days = task.notify_days_before or 0
        scheduled_date = due_date - timedelta(days=notify_days)
        scheduled_for = timezone.make_aware(datetime.combine(scheduled_date, time.min))

        if not application.notify_customer_too:
            return None

        channel = application.notify_customer_channel or application.NOTIFY_CHANNEL_EMAIL
        if channel == application.NOTIFY_CHANNEL_WHATSAPP:
            recipient = application.customer.whatsapp
        else:
            recipient = application.customer.email

        if not recipient:
            return None

        subject = f"Upcoming deadline: {task.name}"
        body = (
            f"Dear {application.customer.full_name},\n\n"
            f"Your next step for application #{application.id} is '{task.name}'.\n"
            f"Due date: {due_date}\n"
            f"Reminder date: {scheduled_for}\n\n"
            f"Notes: {application.notes or '-'}"
        )

        if isinstance(event, dict):
            external_reference = event.get("id", "")
        else:
            external_reference = getattr(event, "id", "") or ""

        notification = WorkflowNotification.objects.create(
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
            doc_application=application,
            doc_workflow=workflow,
            status=WorkflowNotification.STATUS_PENDING,
            scheduled_for=scheduled_for,
            external_reference=external_reference,
        )
        return notification
