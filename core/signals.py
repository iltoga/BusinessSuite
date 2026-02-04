import json
import logging

from django.conf import settings

from core.audit_handlers import PersistentLokiBackend

# Minimal signal forwarding for auditlog LogEntry events -> our Loki backend
# This ensures that we still emit structured logs to Loki when django-auditlog records an event.

_backend = None


def get_backend():
    global _backend
    if _backend is None:
        _backend = PersistentLokiBackend()
    return _backend


# Handlers for emitting structured audit events.
# These are thin wrappers around `PersistentLokiBackend`. They no longer persist to local DB models; django-auditlog is the source of persistent records.


def handle_crud_event(sender, model, instance, event_type, user=None, changes=None):
    """Handle a CRUD event and forward it to the persistent backend.

    Respects `AUDIT_WATCH_CRUD_EVENTS` setting (default: True).
    """
    if not getattr(settings, "AUDIT_WATCH_CRUD_EVENTS", True):
        logging.getLogger(__name__).debug("CRUD events disabled via setting")
        return

    backend = get_backend()
    backend.record_crud(action=event_type, instance=instance, actor=user, changes=changes or {})


def handle_login_event(sender, user=None, event_type="login", ip_address=None):
    """Handle an auth/login event and forward it to the persistent backend.

    Respects `AUDIT_WATCH_AUTH_EVENTS` setting (default: True).
    """
    if not getattr(settings, "AUDIT_WATCH_AUTH_EVENTS", True):
        logging.getLogger(__name__).debug("Auth events disabled via setting")
        return

    backend = get_backend()
    success = event_type == "login"
    backend.record_login(user=user, success=success, ip_address=ip_address)


def handle_request_event(sender, url, method="GET", status_code=None, user=None, duration_ms=None):
    """Handle a request-level event and forward it to the persistent backend.

    Respects `AUDIT_WATCH_REQUEST_EVENTS` and `AUDIT_URL_SKIP_LIST`.
    """
    if not getattr(settings, "AUDIT_WATCH_REQUEST_EVENTS", True):
        logging.getLogger(__name__).debug("Request events disabled via setting")
        return

    skip_list = getattr(settings, "AUDIT_URL_SKIP_LIST", ["/static/", "/media/", "/favicon.ico"])
    if any(url.startswith(p) for p in (skip_list or [])):
        logging.getLogger(__name__).debug("Request URL matched skip list, skipping: %s", url)
        return

    backend = get_backend()
    backend.record_request(method=method, path=url, status_code=status_code, duration_ms=duration_ms, actor=user)


# Listen to auditlog.LogEntry saves (if auditlog is installed) and forward to Loki
try:
    from auditlog.models import LogEntry
    from django.db.models.signals import post_save
    from django.dispatch import receiver

    @receiver(post_save, sender=LogEntry)
    def _forward_auditlog_to_loki(sender, instance, created, **kwargs):
        """Forward django-auditlog LogEntry events to Loki for observability.

        This signal receiver ensures that when django-auditlog creates a LogEntry
        in the database, a corresponding structured log is emitted to Loki via
        the audit logger. This keeps observability in sync with persistent audit
        records.

        Key behaviors:
        - Only processes newly created LogEntry instances (ignores updates).
        - Respects the global AUDIT_ENABLED setting: if audits are disabled at
          runtime, the LogEntry is deleted to prevent any persistent audit data.
        - Builds a structured JSON payload with event details and forwards it
          to Loki using the FailSafeLokiHandler.

        This function is registered automatically when django-auditlog is installed
        and the app is ready. It appears unused in static analysis because it's
        invoked via Django signals, but it's exercised by tests and active in
        production.
        """
        # Only forward when an entry was created
        if not created:
            return
        try:
            backend = get_backend()
            logging.getLogger(__name__).debug(
                "Forwarding auditlog LogEntry to Loki via PersistentLokiBackend (deletion delegated to backend when audits disabled)"
            )
            # Delegate payload construction, emission and deletion behavior to the backend
            backend.record_logentry(entry=instance)
        except Exception:
            logging.getLogger(__name__).exception("Failed to forward auditlog LogEntry to Loki")

except Exception:
    # auditlog not installed — nothing to do
    pass

# Listen to Django auth signals and create auditlog LogEntry records for login events
try:
    from auditlog.models import LogEntry
    from django.contrib.auth import get_user_model
    from django.contrib.auth.signals import user_logged_in, user_login_failed
    from django.contrib.contenttypes.models import ContentType
    from django.dispatch import receiver

    @receiver(user_logged_in)
    def _audit_user_logged_in(sender, request, user, **kwargs):
        """Create an audit log entry when a user successfully logs in."""
        try:
            # Respect global audit toggle: if disabled, do not create DB entries or forward
            from core.audit_handlers import _audit_enabled

            if not _audit_enabled():
                logging.getLogger(__name__).debug("Skipping creation of LogEntry: audits disabled")
                return

            # Create a forced log entry for the user (action=ACCESS)
            LogEntry.objects.log_create(
                user,
                force_log=True,
                action=LogEntry.Action.ACCESS,
                changes={"login": "success"},
                actor=user,
            )
            # Forward to our Loki handler as well
            handle_login_event(
                sender,
                user=user,
                event_type="login",
                ip_address=(getattr(request, "META", {}).get("REMOTE_ADDR") if request is not None else None),
            )
        except Exception:
            logging.getLogger(__name__).exception("Failed to create audit log for user_logged_in")

    @receiver(user_login_failed)
    def _audit_user_login_failed(sender, credentials, request, **kwargs):
        """Create an audit log entry when a login attempt fails."""
        try:
            from core.audit_handlers import _audit_enabled

            if not _audit_enabled():
                logging.getLogger(__name__).debug("Skipping creation of LogEntry for failed login: audits disabled")
                return

            username = credentials.get("username") if isinstance(credentials, dict) else None
            User = get_user_model()
            ct = ContentType.objects.get_for_model(User)

            if username:
                # Try to attribute the failed attempt to an existing user
                try:
                    user = User._default_manager.get_by_natural_key(username)
                    LogEntry.objects.log_create(
                        user,
                        force_log=True,
                        action=LogEntry.Action.ACCESS,
                        changes={"login": "failed"},
                        actor=user,
                    )
                except User.DoesNotExist:
                    # No user found — create a log entry with actor_email filled
                    LogEntry.objects.create(
                        content_type=ct,
                        object_pk=str(username),
                        object_repr=str(username),
                        action=LogEntry.Action.ACCESS,
                        changes={"login": "failed"},
                        actor_email=str(username),
                    )
            else:
                # Generic failed login (no username provided)
                LogEntry.objects.create(
                    content_type=ct,
                    object_pk="",
                    object_repr="login_failed",
                    action=LogEntry.Action.ACCESS,
                    changes={"login": "failed"},
                )

            handle_login_event(
                sender,
                user=None,
                event_type="failed_login",
                ip_address=(getattr(request, "META", {}).get("REMOTE_ADDR") if request is not None else None),
            )
        except Exception:
            logging.getLogger(__name__).exception("Failed to create audit log for user_login_failed")

except Exception:
    # Django auth not available — nothing to do
    pass
