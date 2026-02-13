import os

from core.services.google_calendar_event_colors import GoogleCalendarEventColors
from django.conf import settings
from rest_framework.exceptions import APIException

# Lazy import of google libraries so tests or environments without them fail fast with clear message
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except Exception as e:  # pragma: no cover - environment dependent
    service_account = None
    build = None
    HttpError = Exception

SCOPES = getattr(
    settings,
    "GOOGLE_SCOPES",
    [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/tasks",
    ],
)
SERVICE_ACCOUNT_FILE = getattr(
    settings, "GOOGLE_SERVICE_ACCOUNT_FILE", os.path.join(settings.BASE_DIR, "crm-revisbali-94d3dc9b6077.json")
)
TIMEZONE = getattr(settings, "GOOGLE_TIMEZONE", "Asia/Makassar")
DEFAULT_CALENDAR_ID = getattr(settings, "GOOGLE_CALENDAR_ID", "primary")
DEFAULT_TASKLIST_ID = getattr(settings, "GOOGLE_TASKLIST_ID", "@default")


class GoogleClient:
    """Thin wrapper around Google Calendar and Tasks APIs using a service account.

    Raises APIException when configuration or API errors occur.
    """

    def __init__(self):
        if service_account is None or build is None:
            raise APIException(
                "Google client libraries are not installed. Install `google-auth` and `google-api-python-client`"
            )

        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            raise APIException(f"Service account file not found at: {SERVICE_ACCOUNT_FILE}")

        try:
            self.creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
            self.calendar_service = build("calendar", "v3", credentials=self.creds)
            self.tasks_service = build("tasks", "v1", credentials=self.creds)
        except Exception as e:
            raise APIException(f"Failed to initialize Google client: {e}")

    # --- CALENDAR METHODS ---

    def list_events(
        self,
        calendar_id=None,
        max_results=50,
        time_min=None,
        include_past=False,
        private_extended_property=None,
        query=None,
        fetch_all=False,
    ):
        import datetime

        if calendar_id is None:
            calendar_id = DEFAULT_CALENDAR_ID

        if time_min is None and not include_past:
            # Default to now to show upcoming events
            time_min = datetime.datetime.utcnow().isoformat() + "Z"

        try:
            request_data = {
                "calendarId": calendar_id,
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }
            if time_min:
                request_data["timeMin"] = time_min
            if private_extended_property:
                request_data["privateExtendedProperty"] = private_extended_property
            if query:
                request_data["q"] = query

            items = []
            page_token = None

            while True:
                if page_token:
                    request_data["pageToken"] = page_token
                elif "pageToken" in request_data:
                    request_data.pop("pageToken")

                req = self.calendar_service.events().list(**request_data)
                events_result = req.execute()
                items.extend(events_result.get("items", []))

                page_token = events_result.get("nextPageToken")
                if not fetch_all or not page_token:
                    break

            return items
        except HttpError as e:
            raise APIException(f"Google Calendar Error: {str(e)}")
        except Exception as e:
            raise APIException(f"Google Calendar Error: {str(e)}")

    def get_event(self, event_id, calendar_id=None):
        if calendar_id is None:
            calendar_id = DEFAULT_CALENDAR_ID
        try:
            return self.calendar_service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        except HttpError as e:
            raise APIException(f"Google Calendar Get Error: {str(e)}")
        except Exception as e:
            raise APIException(f"Google Calendar Get Error: {str(e)}")

    def create_event(self, data, calendar_id=None):
        """
        Expects data: { 'summary': str, 'description': str, 'start_time': iso_str|datetime, 'end_time': iso_str|datetime }
        """
        import datetime

        if calendar_id is None:
            calendar_id = DEFAULT_CALENDAR_ID

        start_time = data.get("start_time")
        if isinstance(start_time, (datetime.datetime, datetime.date)):
            start_time = start_time.isoformat()

        end_time = data.get("end_time")
        if isinstance(end_time, (datetime.datetime, datetime.date)):
            end_time = end_time.isoformat()

        start_date = data.get("start_date")
        end_date = data.get("end_date")

        event_body = {
            "summary": data.get("summary"),
            "description": data.get("description", ""),
            "reminders": data.get("reminders")
            or {
                "useDefault": False,
                "overrides": [{"method": "email", "minutes": 60}, {"method": "popup", "minutes": 10}],
            },
        }
        if data.get("extended_properties"):
            event_body["extendedProperties"] = data.get("extended_properties")
        if data.get("colorId") is not None:
            event_body["colorId"] = GoogleCalendarEventColors.validate_color_id(data.get("colorId"))
        elif data.get("color_id") is not None:
            event_body["colorId"] = GoogleCalendarEventColors.validate_color_id(data.get("color_id"))

        if start_date and end_date:
            event_body["start"] = {"date": start_date}
            event_body["end"] = {"date": end_date}
        else:
            event_body["start"] = {"dateTime": start_time, "timeZone": TIMEZONE}
            event_body["end"] = {"dateTime": end_time, "timeZone": TIMEZONE}

        try:
            event = self.calendar_service.events().insert(calendarId=calendar_id, body=event_body).execute()
            return event
        except HttpError as e:
            raise APIException(f"Google Calendar Create Error: {str(e)}")
        except Exception as e:
            raise APIException(f"Google Calendar Create Error: {str(e)}")

    def update_event(self, event_id, data, calendar_id=None):
        import datetime

        if calendar_id is None:
            calendar_id = DEFAULT_CALENDAR_ID

        try:
            body = {}
            if "summary" in data:
                body["summary"] = data["summary"]
            if "description" in data:
                body["description"] = data["description"]
            if "extended_properties" in data:
                body["extendedProperties"] = data["extended_properties"]
            if "colorId" in data:
                body["colorId"] = GoogleCalendarEventColors.validate_color_id(data["colorId"])
            elif "color_id" in data:
                body["colorId"] = GoogleCalendarEventColors.validate_color_id(data["color_id"])

            if "start_time" in data:
                start_time = data["start_time"]
                if isinstance(start_time, (datetime.datetime, datetime.date)):
                    start_time = start_time.isoformat()
                body.setdefault("start", {})["dateTime"] = start_time
                body.setdefault("start", {})["timeZone"] = TIMEZONE

            if "end_time" in data:
                end_time = data["end_time"]
                if isinstance(end_time, (datetime.datetime, datetime.date)):
                    end_time = end_time.isoformat()
                body.setdefault("end", {})["dateTime"] = end_time
                body.setdefault("end", {})["timeZone"] = TIMEZONE

            event = self.calendar_service.events().patch(calendarId=calendar_id, eventId=event_id, body=body).execute()
            return event
        except HttpError as e:
            raise APIException(f"Google Calendar Update Error: {str(e)}")
        except Exception as e:
            raise APIException(f"Google Calendar Update Error: {str(e)}")

    def set_event_color(self, event_id, color_id, calendar_id=None):
        if calendar_id is None:
            calendar_id = DEFAULT_CALENDAR_ID
        validated_color_id = GoogleCalendarEventColors.validate_color_id(color_id)
        return self.update_event(event_id=event_id, data={"color_id": validated_color_id}, calendar_id=calendar_id)

    def set_event_done_state(self, event_id, done: bool, calendar_id=None):
        target_color_id = GoogleCalendarEventColors.color_for_done_state(done)
        return self.set_event_color(event_id=event_id, color_id=target_color_id, calendar_id=calendar_id)

    def delete_event(self, event_id, calendar_id=None):
        if calendar_id is None:
            calendar_id = DEFAULT_CALENDAR_ID
        try:
            self.calendar_service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            return True
        except HttpError as e:
            raise APIException(f"Google Calendar Delete Error: {str(e)}")
        except Exception as e:
            raise APIException(f"Google Calendar Delete Error: {str(e)}")

    # --- TASKS METHODS ---

    def list_tasks(self, tasklist=None):
        if tasklist is None:
            tasklist = DEFAULT_TASKLIST_ID
        try:
            results = self.tasks_service.tasks().list(tasklist=tasklist).execute()
            return results.get("items", [])
        except HttpError as e:
            raise APIException(f"Google Tasks Error: {str(e)}")
        except Exception as e:
            raise APIException(f"Google Tasks Error: {str(e)}")

    def create_task(self, title, notes="", due=None, tasklist=None):
        import datetime

        if tasklist is None:
            tasklist = DEFAULT_TASKLIST_ID

        if isinstance(due, (datetime.datetime, datetime.date)):
            due = due.isoformat()

        body = {"title": title, "notes": notes}
        if due:
            body["due"] = due

        try:
            result = self.tasks_service.tasks().insert(tasklist=tasklist, body=body).execute()
            return result
        except HttpError as e:
            raise APIException(f"Google Tasks Create Error: {str(e)}")
        except Exception as e:
            raise APIException(f"Google Tasks Create Error: {str(e)}")

    def get_task(self, task_id, tasklist=None):
        if tasklist is None:
            tasklist = DEFAULT_TASKLIST_ID
        try:
            return self.tasks_service.tasks().get(tasklist=tasklist, task=task_id).execute()
        except HttpError as e:
            raise APIException(f"Google Tasks Get Error: {str(e)}")
        except Exception as e:
            raise APIException(f"Google Tasks Get Error: {str(e)}")

    def update_task(self, task_id, data, tasklist=None):
        if tasklist is None:
            tasklist = DEFAULT_TASKLIST_ID
        try:
            body = {}
            if "title" in data:
                body["title"] = data["title"]
            if "notes" in data:
                body["notes"] = data["notes"]
            if "due" in data:
                body["due"] = data["due"]
            result = self.tasks_service.tasks().update(tasklist=tasklist, task=task_id, body=body).execute()
            return result
        except HttpError as e:
            raise APIException(f"Google Tasks Update Error: {str(e)}")
        except Exception as e:
            raise APIException(f"Google Tasks Update Error: {str(e)}")

    def delete_task(self, task_id, tasklist=None):
        if tasklist is None:
            tasklist = DEFAULT_TASKLIST_ID
        try:
            self.tasks_service.tasks().delete(tasklist=tasklist, task=task_id).execute()
            return True
        except HttpError as e:
            raise APIException(f"Google Tasks Delete Error: {str(e)}")
        except Exception as e:
            raise APIException(f"Google Tasks Delete Error: {str(e)}")
