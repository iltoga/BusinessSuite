import logging
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.audit_handlers import PersistentOTLPBackend
from core.models.audit import CRUDEvent
from customers.models import Customer


class AuditLoggingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tester", password="secret")
        self.backend = PersistentOTLPBackend()

    def test_record_crud_persists_event_and_logs(self):
        customer = Customer.objects.create(first_name="John", last_name="Doe", email="john@example.com")

        with patch("logging.Logger.info") as mock_info:
            self.backend.record_crud(
                action="create", instance=customer, actor=self.user, changes={"first_name": [None, "John"]}
            )

            # DB record exists
            ev = CRUDEvent.objects.filter(object_type__icontains="Customer", object_id=str(customer.pk)).first()
            self.assertIsNotNone(ev)
            self.assertEqual(ev.action, "create")

            # Logging was attempted
            self.assertTrue(mock_info.called)

    def test_record_crud_handles_db_failure_and_still_logs(self):
        customer = Customer(first_name="Crash", last_name="Test", email="crash@example.com")

        # Simulate DB save error
        with patch.object(CRUDEvent.objects, "create", side_effect=Exception("DB down")):
            with patch("logging.Logger.info") as mock_info:
                # Should not raise even if DB insert fails
                self.backend.record_crud(action="create", instance=customer, actor=self.user, changes={})
                self.assertTrue(mock_info.called)

    def test_otlp_handler_fallback_to_file_on_failure(self):
        # Create a FailSafeOTLPHandler and simulate _primary emitting raising an exception
        from core.audit_handlers import FailSafeOTLPHandler

        handler = FailSafeOTLPHandler(fallback_filename="/tmp/test_audit_degraded.log")
        # monkeypatch the primary to raise
        handler._primary = type("X", (), {"emit": lambda self, r: (_ for _ in ()).throw(Exception("network"))})()
        record = logging.LogRecord("test", logging.ERROR, __file__, 1, "msg", (), None)

        # Ensure no exception is raised and fallback file write happens (file handler emits without error)
        try:
            handler.emit(record)
        except Exception as e:  # pragma: no cover - ensure handler absorbs exceptions
            self.fail(f"OTLP handler fallback raised exception: {e}")
