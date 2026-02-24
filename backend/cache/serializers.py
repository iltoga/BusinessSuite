"""
Cache control API serializers.

Provides serializers for cache status and cache clear operations.
"""

from rest_framework import serializers


class CacheStatusSerializer(serializers.Serializer):
    """Serializer for cache status response."""
    
    enabled = serializers.BooleanField(
        help_text="Whether caching is enabled for the user"
    )
    version = serializers.IntegerField(
        help_text="Current cache version for the user",
        min_value=1
    )
    message = serializers.CharField(
        required=False,
        help_text="Optional status message"
    )
    cache_backend = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Configured default Django cache backend class path",
    )
    cache_location = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Configured default Django cache location",
    )


class CacheClearSerializer(serializers.Serializer):
    """Serializer for cache clear response."""
    
    version = serializers.IntegerField(
        help_text="New cache version after clearing",
        min_value=1
    )
    cleared = serializers.BooleanField(
        help_text="Whether cache was successfully cleared"
    )
    message = serializers.CharField(
        required=False,
        help_text="Optional success message"
    )
