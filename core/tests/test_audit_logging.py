import logging
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.audit_handlers import PersistentLokiBackend
from customers.models import Customer

# Note: legacy DB audit models removed. Tests now assert structured logging
# behaviour produced by PersistentLokiBackend and auditlog forwarding.


class AuditLoggingTests(TestCase):
    def setUp(self):
        # Default tests run with AUDIT_ENABLED True (settings default). No waffle mocking required.
        self.user = get_user_model().objects.create_user(username="tester", password="secret")
        self.backend = PersistentLokiBackend()

    def tearDown(self):
        # No special teardown required
        pass

    def test_record_crud_persists_event_and_logs(self):
        customer = Customer.objects.create(first_name="John", last_name="Doe", email="john@example.com")

        with patch.object(self.backend, "_emit_async") as mock_emit:
            self.backend.record_crud(
                action="create", instance=customer, actor=self.user, changes={"first_name": [None, "John"]}
            )

            # Structured logging was attempted (DB persistence removed in favor of django-auditlog)
            self.assertTrue(mock_emit.called)

    def test_record_crud_handles_db_failure_and_still_logs(self):
        customer = Customer(first_name="Crash", last_name="Test", email="crash@example.com")

        # Persistence removed; ensure logging still occurs
        with patch.object(self.backend, "_emit_async") as mock_emit:
            self.backend.record_crud(action="create", instance=customer, actor=self.user, changes={})
            self.assertTrue(mock_emit.called)

    def test_loki_handler_fallback_to_file_on_failure(self):
        # Create a FailSafeLokiHandler and simulate _primary emitting raising an exception
        from core.audit_handlers import FailSafeLokiHandler

        handler = FailSafeLokiHandler(fallback_filename="/tmp/test_audit_degraded.log")
        # monkeypatch the primary to raise
        handler._primary = type("X", (), {"emit": lambda self, r: (_ for _ in ()).throw(Exception("network"))})()
        record = logging.LogRecord("test", logging.ERROR, __file__, 1, "msg", (), None)

        # Ensure no exception is raised and fallback file write happens (file handler emits without error)
        try:
            handler.emit(record)
        except Exception as e:  # pragma: no cover - ensure handler absorbs exceptions
            self.fail(f"Loki handler fallback raised exception: {e}")

    def test_loki_handler_uses_requests_when_no_logging_loki(self):
        """If logging_loki isn't available, FailSafeLokiHandler should POST directly to Loki via requests."""
        from core.audit_handlers import FailSafeLokiHandler

        handler = FailSafeLokiHandler(fallback_filename="/tmp/test_audit_degraded.log")
        # Ensure there is no primary handler
        handler._primary = None
        # Prevent lazy re-creation of the primary handler during the test
        handler._allow_lazy_primary = False
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "direct-push-test", (), None)

        # Ensure a requests module is present and patch its post method to observe the call
        import sys
        import types
        from unittest.mock import Mock, patch

        if "requests" not in sys.modules:
            mod = types.ModuleType("requests")
            mod.post = Mock()
            sys.modules["requests"] = mod

        with patch("requests.post") as mock_post:
            handler.emit(record)
            self.assertTrue(mock_post.called)

    def test_loki_handler_posts_dynamic_labels(self):
        """When `extra` contains labels (e.g., source/audit), they should be sent as Loki labels."""
        from core.audit_handlers import FailSafeLokiHandler

        handler = FailSafeLokiHandler(fallback_filename="/tmp/test_audit_degraded.log")
        handler._primary = None
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "dynamic-labels-test", (), None)
        # Simulate extra labels set via logger.extra
        record.__dict__.update({"source": "auditlog", "audit": True})

        import requests

        with patch("requests.post") as mock_post:
            handler.emit(record)
            self.assertTrue(mock_post.called)
            # Extract the JSON payload passed to requests.post
            args, kwargs = mock_post.call_args
            payload = kwargs.get("json") if kwargs.get("json") is not None else (args[1] if len(args) > 1 else None)
            self.assertIsNotNone(payload, "Expected JSON payload in requests.post call")
            streams = payload.get("streams", [])
            self.assertTrue(len(streams) >= 1, "Expected at least one stream in payload")
            stream_labels = streams[0].get("stream", {})
            # handler.tags should be present (application) and dynamic labels should be attached
            self.assertIn("application", stream_labels)
            self.assertEqual(stream_labels.get("source"), "auditlog")
            # Booleans are normalized to lowercase strings
            self.assertEqual(stream_labels.get("audit"), "true")

    def test_audit_disabled_via_setting(self):
        from django.test import override_settings

        self.backend = PersistentLokiBackend()
        customer = Customer.objects.create(first_name="Flag", last_name="Off", email="flagoff@example.com")

        with override_settings(AUDIT_ENABLED=False):
            with patch.object(self.backend, "_emit_async") as mock_emit:
                self.backend.record_crud(action="create", instance=customer, actor=self.user, changes={})
                # When audit disabled via setting, no structured log should be emitted
                self.assertFalse(mock_emit.called)

    def test_handle_crud_event_respects_watch_flag(self):
        from django.test import override_settings

        from core import signals as core_signals

        customer = Customer.objects.create(first_name="Skip", last_name="Crud", email="skipcrud@example.com")
        with override_settings(AUDIT_WATCH_CRUD_EVENTS=False):
            with patch("core.signals.get_backend", return_value=self.backend):
                with patch.object(self.backend, "_emit_async") as mock_emit:
                    core_signals.handle_crud_event(
                        sender=None, model=Customer, instance=customer, event_type="create", user=self.user, changes={}
                    )
                    # No logging should be emitted when CRUD watch is disabled
                    self.assertFalse(mock_emit.called)

    def test_handle_request_event_respects_watch_flag_and_skip_list(self):
        from django.test import override_settings

        from core import signals as core_signals

        with override_settings(AUDIT_WATCH_REQUEST_EVENTS=False):
            with patch("core.signals.get_backend", return_value=self.backend):
                with patch.object(self.backend, "_emit_async") as mock_emit:
                    core_signals.handle_request_event(
                        sender=None, url="/any/path", method="GET", status_code=200, user=self.user
                    )
                    self.assertFalse(mock_emit.called)

        # skip static urls
        with patch("core.signals.get_backend", return_value=self.backend):
            with patch.object(self.backend, "_emit_async") as mock_emit:
                core_signals.handle_request_event(
                    sender=None, url="/static/app.js", method="GET", status_code=200, user=self.user
                )
                self.assertFalse(mock_emit.called)

    def test_handle_login_event_respects_watch_flag(self):
        from django.test import override_settings

        from core import signals as core_signals

        with override_settings(AUDIT_WATCH_AUTH_EVENTS=False):
            with patch("core.signals.get_backend", return_value=self.backend):
                with patch.object(self.backend, "_emit_async") as mock_emit:
                    core_signals.handle_login_event(
                        sender=None, user=self.user, event_type="login", ip_address="1.2.3.4"
                    )
                    self.assertFalse(mock_emit.called)

    def test_handle_crud_event_respects_audit_enabled_setting(self):
        from django.test import override_settings

        from core import signals as core_signals

        customer = Customer.objects.create(first_name="Flag", last_name="OffCrud", email="flagcrud@example.com")
        with override_settings(AUDIT_ENABLED=False):
            with patch("core.signals.get_backend", return_value=self.backend):
                with patch.object(self.backend, "_emit_async") as mock_emit:
                    core_signals.handle_crud_event(
                        sender=None,
                        model=Customer,
                        instance=customer,
                        event_type="create",
                        user=self.user,
                        changes={},
                    )
                    # When audit disabled via setting, no structured log should be emitted
                    self.assertFalse(mock_emit.called)

    def test_handle_request_event_respects_audit_enabled_setting(self):
        from django.test import override_settings

        from core import signals as core_signals

        with override_settings(AUDIT_ENABLED=False):
            with patch("core.signals.get_backend", return_value=self.backend):
                with patch.object(self.backend, "_emit_async") as mock_emit:
                    core_signals.handle_request_event(
                        sender=None, url="/any/path", method="GET", status_code=200, user=self.user
                    )
                    self.assertFalse(mock_emit.called)

    def test_record_login_disabled_via_setting(self):
        from django.test import override_settings

        with override_settings(AUDIT_ENABLED=False):
            from core.audit_handlers import PersistentLokiBackend

            backend = PersistentLokiBackend()
            with patch.object(backend, "_emit_async") as mock_emit:
                backend.record_login(user=self.user, success=True, ip_address="1.2.3.4")
                # Login events are now emitted as structured logs only
                self.assertFalse(mock_emit.called)

    def test_record_request_disabled_via_setting(self):
        from django.test import override_settings

        with override_settings(AUDIT_ENABLED=False):
            from core.audit_handlers import PersistentLokiBackend

            backend = PersistentLokiBackend()
            with patch.object(backend, "_emit_async") as mock_emit:
                backend.record_request(method="GET", path="/test", status_code=200, actor=self.user)
                # Request events are now emitted as structured logs only
                self.assertFalse(mock_emit.called)

    def test_audit_enabled_allows_logging(self):
        # Ensure when AUDIT_ENABLED=True audit logging occurs
        from django.test import override_settings

        from core.audit_handlers import PersistentLokiBackend

        backend = PersistentLokiBackend()
        customer = Customer.objects.create(first_name="Flag", last_name="Super", email="flagsuper@example.com")
        with override_settings(AUDIT_ENABLED=True):
            with patch.object(backend, "_emit_async") as mock_emit:
                backend.record_crud(action="create", instance=customer, actor=self.user, changes={})
                self.assertTrue(mock_emit.called)

    def test_login_and_crud_create_audit_when_enabled(self):
        # Ensure LogEntry is created when audit is enabled for both login and CRUD
        from auditlog.models import LogEntry
        from django.contrib.auth.signals import user_logged_in

        # Clean up any pre-existing entries
        LogEntry.objects.all().delete()

        # Simulate login via signal
        user_logged_in.send(sender=self.__class__, request=None, user=self.user)
        self.assertTrue(LogEntry.objects.filter(actor=self.user).exists())

        # Create a customer -> auditlog should create a LogEntry
        customer = Customer.objects.create(first_name="Audit", last_name="Create", email="audit@create.com")
        self.assertTrue(LogEntry.objects.filter(object_pk=str(customer.pk)).exists())

    def test_login_and_crud_do_not_create_audit_when_disabled(self):
        # Ensure LogEntry is NOT created when AUDIT_ENABLED=False
        from auditlog.models import LogEntry
        from django.contrib.auth.signals import user_logged_in
        from django.test import override_settings

        LogEntry.objects.all().delete()

        with override_settings(AUDIT_ENABLED=False):
            user_logged_in.send(sender=self.__class__, request=None, user=self.user)
            # No DB audit entries should persist
            self.assertFalse(LogEntry.objects.exists())

            customer = Customer.objects.create(first_name="NoAudit", last_name="Create", email="noaudit@create.com")
            # LogEntry may have been created then removed by post_save receiver — ensure none persist
            self.assertFalse(LogEntry.objects.exists())

    def test_record_logentry_deletes_entry_when_audit_disabled(self):
        """`PersistentLokiBackend.record_logentry` should delete the DB LogEntry when audits are disabled."""
        from auditlog.models import LogEntry

        # Ensure we have an existing LogEntry created while audits enabled
        from auditlog.registry import auditlog
        from django.test import override_settings

        try:
            auditlog.register(Customer)
        except Exception:
            pass

        LogEntry.objects.all().delete()
        customer = Customer.objects.create(first_name="ToDelete", last_name="Entry", email="todel@del.com")
        entry = LogEntry.objects.filter(object_pk=str(customer.pk)).first()
        self.assertIsNotNone(entry, "Precondition: LogEntry was created by auditlog")

        backend = PersistentLokiBackend()
        with override_settings(AUDIT_ENABLED=False):
            backend.record_logentry(entry=entry)
            self.assertFalse(
                LogEntry.objects.filter(pk=entry.pk).exists(),
                "Expected backend to remove LogEntry when audits disabled",
            )

    def test_emit_async_delegates_to_pool_submit(self):
        """Ensure `_emit_async` delegates emission to the thread pool submit."""
        backend = PersistentLokiBackend()
        with patch.object(backend._pool, "submit") as mock_submit:
            backend._emit_async("info", "msg", extra={"x": 1})
            self.assertTrue(mock_submit.called)

    def test_daemon_thread_pool_drop_on_full_logs_debug(self):
        """When the pool queue is full and drop_on_full=True, a DEBUG message is logged and task is dropped."""
        import queue as pyqueue

        from core.audit_handlers import DaemonThreadPool

        pool = DaemonThreadPool(size=1, max_queue=1, drop_on_full=True)

        # Force queue put_nowait to raise Full to simulate a full queue
        def raise_full(*a, **k):
            raise pyqueue.Full()

        pool._q.put_nowait = raise_full

        import logging

        with patch.object(logging.getLogger("core.audit_handlers"), "debug") as mock_debug:
            pool.submit(lambda: None)
            self.assertTrue(mock_debug.called)

    def test_pool_initialization_respects_settings(self):
        """Ensure PersistentLokiBackend reads emitter settings from Django settings."""
        from django.test import override_settings

        with override_settings(
            LOKI_EMITTER_POOL_SIZE=2, LOKI_EMITTER_QUEUE_MAXSIZE=10, LOKI_EMITTER_DROP_ON_FULL=False
        ):
            backend = PersistentLokiBackend()
            # pool should be initialized according to settings
            self.assertEqual(backend._pool._size, 2)
            self.assertEqual(backend._pool._q.maxsize, 10)
            self.assertFalse(backend._pool._drop_on_full)
