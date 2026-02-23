"""
Cache middleware for injecting cache version headers and managing cache context.

This middleware intercepts requests to:
- Extract authenticated user from request
- Retrieve current cache version for user
- Set cache context attributes on request object
- Add cache version headers to response
- Handle cache bypass for unauthenticated requests

The middleware must be positioned after AuthenticationMiddleware in the
MIDDLEWARE list to ensure request.user is available.
"""

import logging

from django.utils.deprecation import MiddlewareMixin

from .namespace import namespace_manager

logger = logging.getLogger(__name__)


class CacheMiddleware(MiddlewareMixin):
    """
    Middleware that manages cache context for requests and adds cache headers to responses.
    
    This middleware:
    1. Checks if the request has an authenticated user
    2. Retrieves the user's cache version and enabled status
    3. Sets request.cache_version and request.cache_enabled attributes
    4. Adds X-Cache-Version and X-Cache-Enabled headers to responses
    5. Bypasses caching for unauthenticated requests
    
    Request Attributes Set:
        request.cache_version (int): Current cache version for the user
        request.cache_enabled (bool): Whether caching is enabled for the user
    
    Response Headers Added:
        X-Cache-Version: Current user cache version (integer)
        X-Cache-Enabled: Whether caching is enabled (true/false)
    
    Example Usage:
        # In Django settings.py MIDDLEWARE list:
        MIDDLEWARE = [
            ...
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'cache.middleware.CacheMiddleware',  # Must be after auth
            ...
        ]
        
        # In a view:
        def my_view(request):
            if hasattr(request, 'cache_enabled') and request.cache_enabled:
                # Use cached query
                pass
            else:
                # Bypass cache
                pass
    """
    
    def process_request(self, request):
        """
        Process incoming request to set cache context attributes.
        
        Extracts the authenticated user and retrieves their cache version
        and enabled status. Sets these as attributes on the request object
        for use by views and other middleware.
        
        For unauthenticated requests, sets cache_enabled to False to bypass
        all caching operations.
        
        Args:
            request: Django HttpRequest object
            
        Returns:
            None (modifies request in place)
        """
        # Check if user is authenticated
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                user_id = request.user.id
                
                # Get user's cache version
                version = namespace_manager.get_user_version(user_id)
                request.cache_version = version
                
                # Get user's cache enabled status
                enabled = namespace_manager.is_cache_enabled(user_id)
                request.cache_enabled = enabled
                
                logger.debug(
                    f"Cache context set - user_id={user_id}, operation=request_init, "
                    f"version={version}, enabled={enabled}, path={request.path}"
                )
                
            except Exception as e:
                # On error, disable caching for this request
                logger.error(
                    f"Cache error - user_id={request.user.id}, operation=request_init, "
                    f"path={request.path}, error={str(e)}",
                    exc_info=True
                )
                request.cache_enabled = False
                request.cache_version = None
        else:
            # Unauthenticated request - bypass caching
            request.cache_enabled = False
            request.cache_version = None
            logger.debug(
                f"Cache bypassed - operation=request_init, "
                f"reason=unauthenticated, path={request.path}"
            )
    
    def process_response(self, request, response):
        """
        Process outgoing response to add cache headers.
        
        Adds X-Cache-Version and X-Cache-Enabled headers to the response
        if cache context was set during request processing. These headers
        allow the frontend to synchronize its cache with the backend.
        
        Args:
            request: Django HttpRequest object
            response: Django HttpResponse object
            
        Returns:
            Modified HttpResponse with cache headers added
        """
        # Add cache version header if available
        if hasattr(request, 'cache_version') and request.cache_version is not None:
            response['X-Cache-Version'] = str(request.cache_version)
        
        # Add cache enabled header if available
        if hasattr(request, 'cache_enabled'):
            response['X-Cache-Enabled'] = 'true' if request.cache_enabled else 'false'
        
        return response
