"""
Django app configuration for the cache module.

This module configures the cache app and initializes the cacheops wrapper
during Django startup.
"""

from django.apps import AppConfig


class CacheConfig(AppConfig):
    """
    Configuration for the cache Django app.
    
    This app provides:
    - Namespace-based cache versioning for per-user isolation
    - Integration with django-cacheops for automatic query caching
    - O(1) cache invalidation through version increments
    """
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cache'
    verbose_name = 'Cache Management'
    
    def ready(self):
        """
        Initialize cache system when Django starts.
        
        This method:
        1. Configures the cacheops wrapper with namespace integration
        2. Hooks into cacheops key generation
        3. Preserves all cacheops signal handlers
        
        Called once during Django startup.
        """
        # Import here to avoid AppRegistryNotReady errors
        from cache.cacheops_wrapper import cacheops_wrapper
        
        try:
            # Configure cacheops with namespace integration
            cacheops_wrapper.configure_cacheops()
        except ImportError:
            # Cacheops not installed - this is OK, the wrapper will handle it
            pass
        except Exception as e:
            # Log error but don't prevent Django from starting
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error configuring cacheops wrapper: {e}", exc_info=True)
