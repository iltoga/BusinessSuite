import json
import logging

from django.conf import settings
from django.dispatch import receiver

from core.audit_handlers import PersistentOTLPBackend

# Lazy initialization of the backend to avoid issues during startup
_backend = None


def get_backend():
    global _backend
    if _backend is None:
        # Use the backend specified in settings, fallback to default OTLP backend
        backend_path = getattr(settings, "DJANGO_EASY_AUDIT_LOGGING_BACKEND", "core.signals.EasyAuditBackendAdapter")
        if backend_path == "core.audit_handlers.PersistentOTLPBackend":
            _backend = PersistentOTLPBackend()
        else:
            # Dynamically import if a custom one is provided
            import importlib

            module_name, class_name = backend_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            _backend = getattr(module, class_name)()
    return _backend


class EasyAuditBackendAdapter:
    """Adapter to make django-easy-audit backend calls delegate to our PersistentOTLPBackend.

    django-easy-audit expects a backend with methods: `login(self, login_info)`,
    `crud(self, crud_info)`, and `request(self, request_info)`.
    This adapter maps those calls to our `PersistentOTLPBackend` methods.
    """

    def __init__(self):
        self._backend = get_backend()

    def login(self, login_info: dict):
        try:
            user = login_info.get("user")
            success = login_info.get("success", True)
            ip = login_info.get("ip_address") or login_info.get("remote_address") or login_info.get("ip")
            self._backend.record_login(user=user, success=success, ip_address=ip)
        except Exception as exc:  # pragma: no cover - defensive
            logging.exception("EasyAuditBackendAdapter.login failed: %s", exc)
        return login_info

    def crud(self, crud_info: dict):
        try:
            action = crud_info.get("event_type") or crud_info.get("action")
            instance = crud_info.get("instance")
            actor = crud_info.get("user")
            changes = crud_info.get("changes") or {}
            self._backend.record_crud(action=action, instance=instance, actor=actor, changes=changes)
        except Exception as exc:  # pragma: no cover - defensive
            logging.exception("EasyAuditBackendAdapter.crud failed: %s", exc)
        return crud_info

    def request(self, request_info: dict):
        try:
            method = request_info.get("method")
            path = request_info.get("url") or request_info.get("path")
            status = request_info.get("status_code")
            actor = request_info.get("user")
            self._backend.record_request(method=method, path=path, status_code=status, actor=actor)
        except Exception as exc:  # pragma: no cover - defensive
            logging.exception("EasyAuditBackendAdapter.request failed: %s", exc)
        return request_info


# Import signals dynamically to avoid static import errors in editors/type checkers
import importlib

_signals_mod = None
for mod_name in ("easyaudit.signals", "easy_audit.signals"):
    try:
        _signals_mod = importlib.import_module(mod_name)
        break
    except Exception:
        _signals_mod = None

if _signals_mod is not None:
    crud_event = getattr(_signals_mod, "crud_event", None)
    login_event = getattr(_signals_mod, "login_event", None)
    request_event = getattr(_signals_mod, "request_event", None)
else:
    crud_event = login_event = request_event = None

# Register receivers only when signals are available
if crud_event is not None:

    @receiver(crud_event)
    def handle_crud_event(sender, **kwargs):
        backend = get_backend()
        # easy-audit kwargs: model, instance, event_type, user, changes
        backend.record_crud(
            action=kwargs.get("event_type"),
            instance=kwargs.get("instance"),
            actor=kwargs.get("user"),
            changes=kwargs.get("changes"),
        )


if login_event is not None:

    @receiver(login_event)
    def handle_login_event(sender, **kwargs):
        backend = get_backend()
        # easy-audit kwargs: user, event_type, ip_address
        backend.record_login(
            user=kwargs.get("user"), success=kwargs.get("event_type") == "login", ip_address=kwargs.get("ip_address")
        )


if request_event is not None:

    @receiver(request_event)
    def handle_request_event(sender, **kwargs):
        backend = get_backend()
        # easy-audit kwargs: url, method, status_code, user, remote_address
        # Note: duration not provided by easy-audit by default, we'll use performance middleware for that
        backend.record_request(
            method=kwargs.get("method"),
            path=kwargs.get("url"),
            status_code=kwargs.get("status_code"),
            actor=kwargs.get("user"),
        )
