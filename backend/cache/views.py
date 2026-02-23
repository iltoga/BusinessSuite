"""
Cache control API views.

Provides REST API endpoints for users to manage their cache settings:
- GET /api/cache/status - Get current cache status
- POST /api/cache/enable - Enable caching
- POST /api/cache/disable - Disable caching
- POST /api/cache/clear - Clear user cache (O(1) via version increment)

All endpoints require authentication and only allow users to manage their own cache.
"""

import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .namespace import namespace_manager
from .serializers import CacheClearSerializer, CacheStatusSerializer

logger = logging.getLogger(__name__)


class CacheStatusView(APIView):
    """
    Get current cache status for the authenticated user.
    
    Returns:
        200 OK: {enabled: bool, version: int, message: str}
        401 Unauthorized: Not authenticated
        500 Internal Server Error: Redis connection failure
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get cache status for the authenticated user."""
        user_id = request.user.id
        
        try:
            enabled = namespace_manager.is_cache_enabled(user_id)
            version = namespace_manager.get_user_version(user_id)
            
            data = {
                'enabled': enabled,
                'version': version,
                'message': f"Cache is {'enabled' if enabled else 'disabled'}"
            }
            
            serializer = CacheStatusSerializer(data)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(
                f"Error getting cache status for user {user_id}: {e}",
                exc_info=True
            )
            return Response(
                {'error': 'Failed to retrieve cache status'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CacheEnableView(APIView):
    """
    Enable caching for the authenticated user.
    
    Returns:
        200 OK: {enabled: true, version: int, message: str}
        401 Unauthorized: Not authenticated
        500 Internal Server Error: Redis connection failure
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Enable caching for the authenticated user."""
        user_id = request.user.id
        
        try:
            namespace_manager.set_cache_enabled(user_id, True)
            version = namespace_manager.get_user_version(user_id)
            
            data = {
                'enabled': True,
                'version': version,
                'message': 'Cache enabled successfully'
            }
            
            serializer = CacheStatusSerializer(data)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(
                f"Error enabling cache for user {user_id}: {e}",
                exc_info=True
            )
            return Response(
                {'error': 'Failed to enable cache'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CacheDisableView(APIView):
    """
    Disable caching for the authenticated user.
    
    When cache is disabled, all cache operations are bypassed and queries
    execute directly against the database.
    
    Returns:
        200 OK: {enabled: false, message: str}
        401 Unauthorized: Not authenticated
        500 Internal Server Error: Redis connection failure
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Disable caching for the authenticated user."""
        user_id = request.user.id
        
        try:
            namespace_manager.set_cache_enabled(user_id, False)
            
            data = {
                'enabled': False,
                'version': namespace_manager.get_user_version(user_id),
                'message': 'Cache disabled successfully'
            }
            
            serializer = CacheStatusSerializer(data)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(
                f"Error disabling cache for user {user_id}: {e}",
                exc_info=True
            )
            return Response(
                {'error': 'Failed to disable cache'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CacheClearView(APIView):
    """
    Clear cache for the authenticated user via O(1) version increment.
    
    This increments the user's cache version, making all previous cache entries
    inaccessible without requiring key deletion or iteration. This is an O(1)
    operation regardless of cache size.
    
    Returns:
        200 OK: {version: int, cleared: true, message: str}
        401 Unauthorized: Not authenticated
        500 Internal Server Error: Redis connection failure
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Clear cache for the authenticated user."""
        user_id = request.user.id
        
        try:
            # Increment version for O(1) invalidation
            new_version = namespace_manager.increment_user_version(user_id)
            
            data = {
                'version': new_version,
                'cleared': True,
                'message': f'Cache cleared successfully (new version: {new_version})'
            }
            
            serializer = CacheClearSerializer(data)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(
                f"Error clearing cache for user {user_id}: {e}",
                exc_info=True
            )
            return Response(
                {'error': 'Failed to clear cache'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
