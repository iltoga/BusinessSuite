"""Regression tests for idempotency utility helpers."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from api.utils import idempotency
from api.utils.idempotency import IdempotencyConflictError
from django.http import QueryDict
from django.test import SimpleTestCase


class IdempotencyUtilsTests(SimpleTestCase):
    def _make_request(self, *, headers=None, meta=None, data=None, query_params=None, files=None, request_id=None):
        return SimpleNamespace(
            headers=headers or {},
            META=meta or {},
            data=data,
            query_params=query_params,
            FILES=files,
            request_id=request_id,
        )

    def test_normalize_idempotency_key_and_cache_key_are_stable(self):
        self.assertIsNone(idempotency.normalize_idempotency_key(None))
        self.assertIsNone(idempotency.normalize_idempotency_key("   "))
        self.assertEqual(idempotency.normalize_idempotency_key(42), "42")

        cache_key = idempotency.build_async_idempotency_cache_key(
            namespace="backup",
            user_id=7,
            idempotency_key="idem-123",
        )

        self.assertTrue(cache_key.startswith("async-idempotency:backup:7:"))
        self.assertEqual(
            cache_key,
            idempotency.build_async_idempotency_cache_key(
                namespace="backup",
                user_id=7,
                idempotency_key="idem-123",
            ),
        )
        self.assertNotEqual(
            cache_key,
            idempotency.build_async_idempotency_cache_key(
                namespace="backup",
                user_id=7,
                idempotency_key="idem-456",
            ),
        )

    def test_get_request_idempotency_key_prefers_headers_and_falls_back_to_meta(self):
        request_with_header = self._make_request(
            headers={"Idempotency-Key": "  header-key  "},
            meta={"HTTP_IDEMPOTENCY_KEY": "meta-key"},
            data={"idempotency_key": "body-key"},
            query_params=QueryDict("idempotency_key=query-key"),
        )
        self.assertEqual(idempotency.get_request_idempotency_key(request_with_header), "header-key")

        fallback_request = self._make_request(
            meta={"HTTP_IDEMPOTENCY_KEY": "  meta-key  "},
            data={"idempotency_key": "body-key"},
            query_params=QueryDict("idempotencyKey=query-key"),
        )
        self.assertEqual(idempotency.get_request_idempotency_key(fallback_request), "meta-key")

    def test_build_request_idempotency_fingerprint_ignores_idempotency_fields_and_normalizes_nested_values(self):
        file_one = SimpleNamespace(
            name="passport.png",
            size=1024,
            content_type="image/png",
            content_type_extra={"quality": "high"},
            read=lambda: b"",
        )
        file_two = SimpleNamespace(
            name="passport.png",
            size=1024,
            content_type="image/png",
            content_type_extra={"quality": "high"},
            read=lambda: b"",
        )

        request_a = self._make_request(
            query_params=QueryDict("page=1&idempotency_key=ignored"),
            data={
                "idempotency_key": "ignored",
                "customer": {
                    "idempotencyKey": "ignored",
                    "when": date(2026, 3, 21),
                },
                "tags": {"beta", "alpha"},
                "items": [1, {"status": "open"}],
            },
            files={"upload": file_one},
        )
        request_b = self._make_request(
            query_params=QueryDict("page=1&idempotency_key=different"),
            data={
                "idempotencyKey": "different",
                "customer": {
                    "idempotency_key": "different",
                    "when": date(2026, 3, 21),
                },
                "tags": {"alpha", "beta"},
                "items": [1, {"status": "open"}],
            },
            files={"upload": file_two},
        )

        fingerprint_a = idempotency.build_request_idempotency_fingerprint(request_a)
        fingerprint_b = idempotency.build_request_idempotency_fingerprint(request_b)

        self.assertIsNotNone(fingerprint_a)
        self.assertEqual(fingerprint_a, fingerprint_b)

    def test_claim_request_idempotency_reuses_cached_hit_and_detects_payload_mismatch(self):
        request = self._make_request(headers={"Idempotency-Key": "idem-123"}, request_id="req-123")
        cache_key = idempotency.build_async_idempotency_cache_key(
            namespace="backup_start_sse",
            user_id=99,
            idempotency_key="idem-123",
        )

        with patch.object(
            idempotency.cache, "get", return_value={"kind": "claim", "fingerprint": "fp-1"}
        ), patch.object(idempotency.cache, "add") as cache_add:
            resolved_cache_key, deduplicated = idempotency.claim_request_idempotency(
                request=request,
                namespace="backup_start_sse",
                user_id=99,
                fingerprint="fp-1",
            )

        self.assertEqual(resolved_cache_key, cache_key)
        self.assertTrue(deduplicated)
        cache_add.assert_not_called()

        with patch.object(idempotency.cache, "get", return_value={"kind": "claim", "fingerprint": "old-fp"}):
            with self.assertRaises(IdempotencyConflictError):
                idempotency.claim_request_idempotency(
                    request=request,
                    namespace="backup_start_sse",
                    user_id=99,
                    fingerprint="new-fp",
                )

    def test_claim_request_idempotency_returns_false_for_new_claim(self):
        request = self._make_request(headers={"Idempotency-Key": "idem-456"}, request_id="req-456")

        with patch.object(idempotency.cache, "get", return_value=None), patch.object(
            idempotency.cache, "add", return_value=True
        ) as cache_add:
            cache_key, deduplicated = idempotency.claim_request_idempotency(
                request=request,
                namespace="backup_start_sse",
                user_id=99,
                fingerprint="fp-2",
            )

        self.assertTrue(cache_key.startswith("async-idempotency:backup_start_sse:99:"))
        self.assertFalse(deduplicated)
        cache_add.assert_called_once()

    def test_resolve_request_idempotent_job_returns_job_and_clears_stale_records(self):
        cached_job = SimpleNamespace(id="job-123")
        queryset = Mock()
        queryset.filter.return_value.first.return_value = cached_job

        with patch.object(
            idempotency.cache,
            "get",
            return_value={"kind": "job", "fingerprint": "fp-1", "job_id": "job-123"},
        ), patch.object(idempotency.cache, "delete") as cache_delete:
            resolved_job = idempotency.resolve_request_idempotent_job(
                request=self._make_request(headers={"Idempotency-Key": "idem-123"}, request_id="req-123"),
                namespace="backup_start_sse",
                user_id=99,
                queryset=queryset,
                fingerprint="fp-1",
            )[1]

        self.assertEqual(resolved_job, cached_job)
        cache_delete.assert_not_called()
        queryset.filter.assert_called_once_with(id="job-123")

        stale_queryset = Mock()
        stale_queryset.filter.return_value.first.return_value = None

        with patch.object(
            idempotency.cache,
            "get",
            return_value={"kind": "job", "fingerprint": "fp-1", "job_id": "job-123"},
        ), patch.object(idempotency.cache, "delete") as cache_delete:
            resolved_job = idempotency.resolve_request_idempotent_job(
                request=self._make_request(headers={"Idempotency-Key": "idem-123"}, request_id="req-123"),
                namespace="backup_start_sse",
                user_id=99,
                queryset=stale_queryset,
                fingerprint="fp-1",
            )[1]

        self.assertIsNone(resolved_job)
        cache_delete.assert_called_once()
