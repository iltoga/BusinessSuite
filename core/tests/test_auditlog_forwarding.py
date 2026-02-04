from unittest.mock import patch

from auditlog.registry import auditlog
from django.conf import settings
from django.test import TestCase

from core.audit_handlers import PersistentLokiBackend
from customers.models import Customer


class AuditlogForwardingTests(TestCase):
    def setUp(self):
        # Ensure the model is registered with auditlog for tests
        try:
            auditlog.register(Customer)
        except Exception:
            pass

        # Ensure AUDIT_ENABLED is True by default in tests (settings default). No waffle Switch required.
        assert getattr(settings, "AUDIT_ENABLED", True) is True

    def test_logentry_forwarded_to_loki_on_create(self):
        backend = PersistentLokiBackend()

        with patch("core.signals.get_backend", return_value=backend):
            with patch.object(backend, "_emit_async") as mock_emit:
                # create a new customer -> auditlog should create a LogEntry which our signal forwards
                Customer.objects.create(first_name="A", last_name="B", email="a@b.com")
                self.assertTrue(mock_emit.called, "Expected forwarding to Loki on auditlog LogEntry creation")

    def test_no_forward_when_disabled_via_setting(self):
        from django.test import override_settings

        backend = PersistentLokiBackend()
        with override_settings(AUDIT_ENABLED=False):
            with patch("core.signals.get_backend", return_value=backend):
                with patch.object(backend.logger, "info") as mock_info:
                    Customer.objects.create(first_name="A", last_name="C", email="a@c.com")
                    self.assertFalse(mock_info.called)

    def test_forwarder_delegates_to_backend_record_logentry(self):
        """Ensure the LogEntry forwarder delegates payload construction to the backend."""
        backend = PersistentLokiBackend()
        with patch("core.signals.get_backend", return_value=backend):
            with patch.object(backend, "record_logentry") as mock_record:
                Customer.objects.create(first_name="X", last_name="Y", email="x@y.com")
                self.assertTrue(mock_record.called, "Expected signal to call backend.record_logentry")

    def test_record_logentry_emits_tagged_audit_payload(self):
        """Ensure audit LogEntry emissions are tagged for Grafana filtering."""
        backend = PersistentLokiBackend()
        try:
            from auditlog.registry import auditlog

            auditlog.register(Customer)
        except Exception:
            pass

        with patch.object(backend, "_emit_async") as mock_emit:
            Customer.objects.create(first_name="T", last_name="A", email="t@a.com")
            # Find created LogEntry
            from auditlog.models import LogEntry

            entry = LogEntry.objects.filter(object_pk__isnull=False).order_by("-pk").first()
            self.assertIsNotNone(entry)

            backend.record_logentry(entry=entry)
            self.assertTrue(mock_emit.called)
            called_args = mock_emit.call_args[0]
            called_kwargs = mock_emit.call_args[1]
            # (level, message) and extra passed as kwarg
            self.assertEqual(called_args[0], "info")
            self.assertIsInstance(called_args[1], str)
            self.assertIn("extra", called_kwargs)
            self.assertIn("source", called_kwargs["extra"])
            self.assertEqual(called_kwargs["extra"]["source"], "auditlog")
            self.assertTrue(called_kwargs["extra"].get("audit", False))

    def test_forwarding_disabled_via_setting(self):
        from django.test import override_settings

        backend = PersistentLokiBackend()
        try:
            from auditlog.registry import auditlog

            auditlog.register(Customer)
        except Exception:
            pass

        with patch.object(backend, "_emit_async") as mock_emit:
            with override_settings(AUDIT_FORWARD_TO_LOKI=False):
                Customer.objects.create(first_name="No", last_name="Forward", email="nof@fwd.com")
                from auditlog.models import LogEntry

                entry = LogEntry.objects.filter(object_pk__isnull=False).order_by("-pk").first()
                self.assertIsNotNone(entry)

                backend.record_logentry(entry=entry)
                self.assertFalse(mock_emit.called, "Expected no emission when AUDIT_FORWARD_TO_LOKI is False")
