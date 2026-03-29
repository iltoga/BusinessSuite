"""Tests for the document expiration state service."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from customer_applications.services.document_expiration_state_service import DocumentExpirationStateService
from django.test import SimpleTestCase


class DocumentExpirationStateServiceTests(SimpleTestCase):
    def setUp(self):
        self.service = DocumentExpirationStateService()

    def test_threshold_days_sanitizes_invalid_values(self):
        self.assertEqual(self.service._threshold_days(SimpleNamespace(expiring_threshold_days="7")), 7)
        self.assertEqual(self.service._threshold_days(SimpleNamespace(expiring_threshold_days=None)), 0)
        self.assertEqual(self.service._threshold_days(SimpleNamespace(expiring_threshold_days=-2)), 0)
        self.assertEqual(self.service._threshold_days(SimpleNamespace(expiring_threshold_days="bad")), 0)

    def test_evaluate_returns_ok_when_no_expiration_or_non_expiring_type(self):
        with patch(
            "customer_applications.services.document_expiration_state_service.timezone.localdate",
            return_value=date(2026, 3, 20),
        ):
            no_expiration = self.service.evaluate(
                SimpleNamespace(
                    expiration_date=None,
                    doc_type=SimpleNamespace(has_expiration_date=True, expiring_threshold_days=5),
                )
            )
            no_expiration_type = self.service.evaluate(
                SimpleNamespace(
                    expiration_date=date(2026, 3, 25),
                    doc_type=SimpleNamespace(has_expiration_date=False, expiring_threshold_days=5),
                )
            )

        self.assertEqual(no_expiration.state, self.service.STATE_OK)
        self.assertFalse(no_expiration.is_invalid)
        self.assertEqual(no_expiration_type.state, self.service.STATE_OK)
        self.assertFalse(no_expiration_type.is_invalid)

    def test_evaluate_returns_expired_and_expiring_states(self):
        with patch(
            "customer_applications.services.document_expiration_state_service.timezone.localdate",
            return_value=date(2026, 3, 20),
        ):
            expired = self.service.evaluate(
                SimpleNamespace(
                    expiration_date=date(2026, 3, 19),
                    doc_type=SimpleNamespace(has_expiration_date=True, expiring_threshold_days=5),
                )
            )
            expiring = self.service.evaluate(
                SimpleNamespace(
                    expiration_date=date(2026, 3, 24),
                    doc_type=SimpleNamespace(has_expiration_date=True, expiring_threshold_days=5),
                )
            )

        self.assertEqual(expired.state, self.service.STATE_EXPIRED)
        self.assertTrue(expired.is_invalid)
        self.assertIn("expired on 2026-03-19", expired.reason)
        self.assertEqual(expiring.state, self.service.STATE_EXPIRING)
        self.assertTrue(expiring.is_invalid)
        self.assertIn("within 5 days", expiring.reason)
