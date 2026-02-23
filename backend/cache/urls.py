"""
Cache control API URL configuration.

Defines URL patterns for cache management endpoints:
- GET /api/cache/status/ - Get current cache status
- POST /api/cache/enable/ - Enable caching
- POST /api/cache/disable/ - Disable caching
- POST /api/cache/clear/ - Clear user cache
"""

from django.urls import path

from .views import (
    CacheClearView,
    CacheDisableView,
    CacheEnableView,
    CacheStatusView,
)

app_name = 'cache'

urlpatterns = [
    path('status/', CacheStatusView.as_view(), name='status'),
    path('enable/', CacheEnableView.as_view(), name='enable'),
    path('disable/', CacheDisableView.as_view(), name='disable'),
    path('clear/', CacheClearView.as_view(), name='clear'),
]
