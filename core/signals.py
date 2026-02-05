"""Signals module — register minimal DB-only login audit receivers.

We avoid any forwarding to Loki or local files. Login events are recorded
in the DB via `django-auditlog` when `AUDIT_ENABLED` and
`AUDIT_WATCH_AUTH_EVENTS` are enabled.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.contrib.contenttypes.models import ContentType
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# Import auditlog LogEntry lazily and guard when auditlog is not installed
try:
    from auditlog.models import LogEntry  # type: ignore
except Exception:
    LogEntry = None  # pragma: no cover - safe fallback when auditlog isn't available


@receiver(user_logged_in)
def _audit_user_logged_in(sender, request, user, **kwargs):
    """Create a DB-only LogEntry when a user successfully logs in.

    Respects `AUDIT_ENABLED` and `AUDIT_WATCH_AUTH_EVENTS` settings.
    """
    try:
        if not getattr(settings, "AUDIT_ENABLED", True) or not getattr(settings, "AUDIT_WATCH_AUTH_EVENTS", True):
            return
        if LogEntry is None:
            return

        # Use `log_create` to ensure consistent content_type/object_pk mapping
        # Use [old, new] style for `changes` so admin displays it as a single field change
        LogEntry.objects.log_create(
            instance=user,
            action=LogEntry.Action.ACCESS,
            changes={"login": [None, "success"]},
            actor=user,
            force_log=True,
            remote_addr=(getattr(request, "META", {}).get("REMOTE_ADDR") if request is not None else None),
        )
    except Exception:
        logger.exception("Failed to create audit LogEntry for user_logged_in")


@receiver(user_login_failed)
def _audit_user_login_failed(sender, credentials, request, **kwargs):
    """Create a DB-only LogEntry when a login attempt fails.

    If the username maps to an existing user, attribute the event to that
    user. Otherwise create a LogEntry with `actor_email` populated.
    """
    try:
        if not getattr(settings, "AUDIT_ENABLED", True) or not getattr(settings, "AUDIT_WATCH_AUTH_EVENTS", True):
            return
        if LogEntry is None:
            return

        username = credentials.get("username") if isinstance(credentials, dict) else None
        User = get_user_model()
        ct = ContentType.objects.get_for_model(User)

        if username:
            try:
                user = User._default_manager.get_by_natural_key(username)
                LogEntry.objects.log_create(
                    instance=user,
                    action=LogEntry.Action.ACCESS,
                    changes={"login": [None, "failed"]},
                    actor=user,
                    force_log=True,
                    remote_addr=(getattr(request, "META", {}).get("REMOTE_ADDR") if request is not None else None),
                )
            except User.DoesNotExist:
                LogEntry.objects.create(
                    content_type=ct,
                    object_pk=str(username),
                    object_repr=str(username),
                    action=LogEntry.Action.ACCESS,
                    changes={"login": [None, "failed"]},
                    actor_email=str(username),
                )
        else:
            LogEntry.objects.create(
                content_type=ct,
                object_pk="",
                object_repr="login_failed",
                action=LogEntry.Action.ACCESS,
                changes={"login": [None, "failed"]},
            )
    except Exception:
        logger.exception("Failed to create audit LogEntry for user_login_failed")
