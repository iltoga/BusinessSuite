"""Property-based tests for cache error handling and resilience.

Feature: hybrid-cache-system, Properties 17, 18, 19, 28
"""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from cache.cacheops_wrapper import CacheopsWrapper, _thread_local


class TestErrorHandlingProperties(HypothesisTestCase):
    """Property tests for backend cache resilience behavior."""

    def setUp(self):
        self.wrapper = CacheopsWrapper()
        self.wrapper._cacheops_configured = True
        if hasattr(_thread_local, "user_id"):
            delattr(_thread_local, "user_id")

    def tearDown(self):
        if hasattr(_thread_local, "user_id"):
            delattr(_thread_local, "user_id")

    @given(user_id=st.integers(min_value=1, max_value=1_000_000))
    @settings(max_examples=50)
    @patch("cache.cacheops_wrapper.namespace_manager")
    def test_property_17_redis_connection_failure_fallback(self, mock_ns_manager, user_id):
        """Property 17: Redis connection failure fallback."""
        self.wrapper.namespace_manager = mock_ns_manager
        mock_ns_manager.is_cache_enabled.side_effect = ConnectionError("Redis unavailable")

        queryset = MagicMock()
        queryset.model = type("TestModel", (), {})
        queryset.__iter__ = MagicMock(return_value=iter([1, 2, 3]))

        result = self.wrapper.get_cached_query(queryset, user_id=user_id)
        assert result == [1, 2, 3]

    @given(
        user_id=st.integers(min_value=1, max_value=1_000_000),
        error_msg=st.sampled_from(
            [
                "Failed to serialize object",
                "serialization error",
                "pickle serialization failed",
            ]
        ),
    )
    @settings(max_examples=30)
    @patch("cache.cacheops_wrapper.namespace_manager")
    def test_property_18_serialization_failure_fallback(self, mock_ns_manager, user_id, error_msg):
        """Property 18: Serialization failure fallback."""
        self.wrapper.namespace_manager = mock_ns_manager
        mock_ns_manager.is_cache_enabled.return_value = True
        mock_ns_manager.get_cache_key_prefix.return_value = f"cache:{user_id}:v1:cacheops:"

        queryset = MagicMock()
        queryset.model = type("TestModel", (), {})

        call_count = {"n": 0}

        def query_iter():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ValueError(error_msg)
            return iter([42])

        queryset.__iter__ = MagicMock(side_effect=query_iter)

        result = self.wrapper.get_cached_query(queryset, user_id=user_id)
        assert result == [42]

    @given(
        user_id=st.integers(min_value=1, max_value=1_000_000),
        error_msg=st.sampled_from(
            [
                "Failed to deserialize data",
                "unpickling error",
                "corrupted cache payload",
            ]
        ),
    )
    @settings(max_examples=30)
    @patch("cache.cacheops_wrapper.namespace_manager")
    @patch("cache.cacheops_wrapper.cache")
    def test_property_19_deserialization_failure_recovery(
        self, mock_cache_backend, mock_ns_manager, user_id, error_msg
    ):
        """Property 19: Deserialization failure recovery."""
        self.wrapper.namespace_manager = mock_ns_manager
        mock_ns_manager.is_cache_enabled.return_value = True
        mock_ns_manager.get_cache_key_prefix.return_value = f"cache:{user_id}:v1:cacheops:"

        queryset = MagicMock()
        queryset.model = type("TestModel", (), {})

        call_count = {"n": 0}

        def query_iter():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ValueError(error_msg)
            return iter([7, 8, 9])

        queryset.__iter__ = MagicMock(side_effect=query_iter)

        result = self.wrapper.get_cached_query(queryset, user_id=user_id)
        assert result == [7, 8, 9]
        assert mock_cache_backend.delete.called

    @given(
        user_id=st.integers(min_value=1, max_value=1_000_000),
        primary_error=st.sampled_from(
            [
                ConnectionError("redis down"),
                TimeoutError("redis timeout"),
                ValueError("Failed to serialize object"),
                ValueError("Failed to deserialize data"),
                RuntimeError("unexpected cache failure"),
            ]
        ),
        fallback_fails=st.booleans(),
    )
    @settings(max_examples=60)
    @patch("cache.cacheops_wrapper.namespace_manager")
    def test_property_28_no_unhandled_cache_exceptions(
        self, mock_ns_manager, user_id, primary_error, fallback_fails
    ):
        """Property 28: No unhandled cache exceptions."""
        self.wrapper.namespace_manager = mock_ns_manager
        mock_ns_manager.is_cache_enabled.return_value = True
        mock_ns_manager.get_cache_key_prefix.return_value = f"cache:{user_id}:v1:cacheops:"

        queryset = MagicMock()
        queryset.model = type("TestModel", (), {})

        call_count = {"n": 0}

        def query_iter():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise primary_error
            if fallback_fails:
                raise RuntimeError("database fallback failed")
            return iter([99])

        queryset.__iter__ = MagicMock(side_effect=query_iter)

        result = self.wrapper.get_cached_query(queryset, user_id=user_id)
        if fallback_fails:
            assert result == []
        else:
            assert result == [99]
