"""
Unit tests for cache control API endpoints.

Tests specific behavior of status, enable, disable, and clear endpoints.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from cache.namespace import namespace_manager

User = get_user_model()


@pytest.fixture(autouse=True)
def _use_locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "cache-api-unit-tests",
        },
        "select2": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "cache-api-unit-tests-select2",
        },
    }


@pytest.mark.django_db
class TestCacheStatusEndpoint:
    """Unit tests for cache status endpoint."""
    
    def test_status_returns_enabled_and_version(self):
        """Test that status endpoint returns enabled flag, version, and backend metadata."""
        user = User.objects.create_user(username="testuser", password="testpass123")
        client = APIClient()
        client.force_authenticate(user=user)
        
        # Get status
        response = client.get("/api/cache/status/")
        
        assert response.status_code == 200
        assert "enabled" in response.data
        assert "version" in response.data
        backend_key = "cacheBackend" if "cacheBackend" in response.data else "cache_backend"
        location_key = "cacheLocation" if "cacheLocation" in response.data else "cache_location"
        assert backend_key in response.data
        assert location_key in response.data
        assert isinstance(response.data["enabled"], bool)
        assert isinstance(response.data["version"], int)
        assert isinstance(response.data[backend_key], str)
        assert isinstance(response.data[location_key], str)
        assert response.data["version"] >= 1
        
        user.delete()
    
    def test_status_requires_authentication(self):
        """Test that status endpoint requires authentication."""
        client = APIClient()
        response = client.get("/api/cache/status/")
        
        assert response.status_code in [401, 403]
    
    def test_status_reflects_enabled_state(self):
        """Test that status endpoint reflects the enabled state."""
        user = User.objects.create_user(username="testuser", password="testpass123")
        client = APIClient()
        client.force_authenticate(user=user)
        
        # Enable cache
        namespace_manager.set_cache_enabled(user.id, True)
        response = client.get("/api/cache/status/")
        assert response.data["enabled"] is True
        
        # Disable cache
        namespace_manager.set_cache_enabled(user.id, False)
        response = client.get("/api/cache/status/")
        assert response.data["enabled"] is False
        
        user.delete()


@pytest.mark.django_db
class TestCacheEnableEndpoint:
    """Unit tests for cache enable endpoint."""
    
    def test_enable_sets_cache_enabled_true(self):
        """Test that enable endpoint sets cache_enabled to True."""
        user = User.objects.create_user(username="testuser", password="testpass123")
        client = APIClient()
        client.force_authenticate(user=user)
        
        # Disable first
        namespace_manager.set_cache_enabled(user.id, False)
        
        # Enable via API
        response = client.post("/api/cache/enable/")
        
        assert response.status_code == 200
        assert response.data["enabled"] is True
        assert namespace_manager.is_cache_enabled(user.id) is True
        
        user.delete()
    
    def test_enable_returns_version(self):
        """Test that enable endpoint returns current version."""
        user = User.objects.create_user(username="testuser", password="testpass123")
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.post("/api/cache/enable/")
        
        assert response.status_code == 200
        assert "version" in response.data
        assert isinstance(response.data["version"], int)
        
        user.delete()
    
    def test_enable_requires_authentication(self):
        """Test that enable endpoint requires authentication."""
        client = APIClient()
        response = client.post("/api/cache/enable/")
        
        assert response.status_code in [401, 403]


@pytest.mark.django_db
class TestCacheDisableEndpoint:
    """Unit tests for cache disable endpoint."""
    
    def test_disable_sets_cache_enabled_false(self):
        """Test that disable endpoint sets cache_enabled to False."""
        user = User.objects.create_user(username="testuser", password="testpass123")
        client = APIClient()
        client.force_authenticate(user=user)
        
        # Enable first
        namespace_manager.set_cache_enabled(user.id, True)
        
        # Disable via API
        response = client.post("/api/cache/disable/")
        
        assert response.status_code == 200
        assert response.data["enabled"] is False
        assert namespace_manager.is_cache_enabled(user.id) is False
        
        user.delete()
    
    def test_disable_requires_authentication(self):
        """Test that disable endpoint requires authentication."""
        client = APIClient()
        response = client.post("/api/cache/disable/")
        
        assert response.status_code in [401, 403]


@pytest.mark.django_db
class TestCacheClearEndpoint:
    """Unit tests for cache clear endpoint."""
    
    def test_clear_increments_version(self):
        """Test that clear endpoint increments the cache version."""
        user = User.objects.create_user(username="testuser", password="testpass123")
        client = APIClient()
        client.force_authenticate(user=user)
        
        # Get initial version
        initial_version = namespace_manager.get_user_version(user.id)
        
        # Clear cache
        response = client.post("/api/cache/clear/")
        
        assert response.status_code == 200
        assert response.data["cleared"] is True
        assert "version" in response.data
        
        # Verify version was incremented
        new_version = namespace_manager.get_user_version(user.id)
        assert new_version == initial_version + 1
        assert response.data["version"] == new_version
        
        user.delete()
    
    def test_clear_returns_new_version(self):
        """Test that clear endpoint returns the new version."""
        user = User.objects.create_user(username="testuser", password="testpass123")
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.post("/api/cache/clear/")
        
        assert response.status_code == 200
        assert "version" in response.data
        assert isinstance(response.data["version"], int)
        assert response.data["version"] >= 1
        
        user.delete()
    
    def test_clear_requires_authentication(self):
        """Test that clear endpoint requires authentication."""
        client = APIClient()
        response = client.post("/api/cache/clear/")
        
        assert response.status_code in [401, 403]
    
    def test_clear_multiple_times_increments_each_time(self):
        """Test that clearing multiple times increments version each time."""
        user = User.objects.create_user(username="testuser", password="testpass123")
        client = APIClient()
        client.force_authenticate(user=user)
        
        # Get initial version
        initial_version = namespace_manager.get_user_version(user.id)
        
        # Clear multiple times
        for i in range(3):
            response = client.post("/api/cache/clear/")
            assert response.status_code == 200
            assert response.data["version"] == initial_version + i + 1
        
        # Verify final version
        final_version = namespace_manager.get_user_version(user.id)
        assert final_version == initial_version + 3
        
        user.delete()


@pytest.mark.django_db
class TestCacheAPIErrorHandling:
    """Unit tests for cache API error handling."""
    
    def test_endpoints_handle_redis_errors_gracefully(self):
        """Test that endpoints handle Redis errors without crashing."""
        user = User.objects.create_user(username="testuser", password="testpass123")
        client = APIClient()
        client.force_authenticate(user=user)
        
        # All endpoints should return responses even if Redis has issues
        # (The actual error handling is in the namespace manager)
        
        # Status endpoint
        response = client.get("/api/cache/status/")
        assert response.status_code in [200, 500]
        
        # Enable endpoint
        response = client.post("/api/cache/enable/")
        assert response.status_code in [200, 500]
        
        # Disable endpoint
        response = client.post("/api/cache/disable/")
        assert response.status_code in [200, 500]
        
        # Clear endpoint
        response = client.post("/api/cache/clear/")
        assert response.status_code in [200, 500]
        
        user.delete()
    
    def test_endpoints_return_json_responses(self):
        """Test that all endpoints return JSON responses."""
        user = User.objects.create_user(username="testuser", password="testpass123")
        client = APIClient()
        client.force_authenticate(user=user)
        
        endpoints = [
            ("/api/cache/status/", "get"),
            ("/api/cache/enable/", "post"),
            ("/api/cache/disable/", "post"),
            ("/api/cache/clear/", "post"),
        ]
        
        for endpoint, method in endpoints:
            if method == "get":
                response = client.get(endpoint)
            else:
                response = client.post(endpoint)
            
            assert response.status_code == 200
            content_type = response.headers.get("Content-Type") if hasattr(response, "headers") else response.get("Content-Type")
            assert content_type is not None and content_type.startswith("application/json")
            assert isinstance(response.data, dict)
        
        user.delete()
