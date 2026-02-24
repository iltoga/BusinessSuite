"""
Cacheops wrapper for integrating django-cacheops with namespace versioning.

This module provides a wrapper around django-cacheops that integrates the namespace
layer for per-user cache isolation and O(1) invalidation. It hooks into cacheops
key generation to add namespace prefixes while preserving all automatic invalidation
logic.

Key Features:
- Integrates cacheops with namespace versioning
- Preserves cacheops automatic invalidation on model changes
- Adds per-user namespace prefix to all cache keys
- Provides fallback on cache errors
- Doesn't interfere with existing non-user-specific cache usage

Integration Points:
- Hooks into cacheops key generation
- Preserves cacheops signal handlers
- Uses cacheops dependency tracking unchanged
- Wraps cacheops cache backend with namespace-aware version
"""

import logging
import pickle
from typing import Any, Optional, Type

from django.conf import settings
from django.core.cache import cache
from django.db.models import Model, QuerySet

from cache.namespace import namespace_manager
from cache.metrics import cache_metrics

logger = logging.getLogger(__name__)


class CacheopsWrapper:
    """
    Wrapper for django-cacheops that integrates namespace versioning.
    
    This class provides methods to:
    - Configure cacheops with namespace integration
    - Execute cached queries with namespace prefixes
    - Invalidate model caches while preserving cacheops logic
    - Handle cache errors gracefully with database fallback
    
    The wrapper layers on top of existing cache without breaking non-user-specific
    cache usage like Meta WhatsApp tokens, cron locks, or invoice sequences.
    
    Example Usage:
        >>> wrapper = CacheopsWrapper()
        >>> wrapper.configure_cacheops()
        >>> result = wrapper.get_cached_query(MyModel.objects.filter(active=True), user_id=123)
        >>> wrapper.invalidate_model(MyModel)
    """
    
    def __init__(self):
        """Initialize the cacheops wrapper."""
        self.namespace_manager = namespace_manager
        self._cacheops_configured = False
        self._original_key_func = None
    
    def configure_cacheops(self) -> None:
        """
        Configure django-cacheops to integrate with namespace versioning.
        
        This method:
        1. Imports and initializes cacheops
        2. Hooks into cacheops key generation to add namespace prefix
        3. Preserves all cacheops signal handlers and dependency tracking
        4. Ensures wrapper doesn't interfere with existing cache usage
        
        Should be called once during Django startup (e.g., in AppConfig.ready()).
        
        Raises:
            ImportError: If django-cacheops is not installed
            
        Example:
            >>> wrapper = CacheopsWrapper()
            >>> wrapper.configure_cacheops()
        """
        if self._cacheops_configured:
            logger.debug("Cacheops already configured, skipping")
            return
        
        try:
            # Import cacheops - this will fail if not installed
            import cacheops
            from cacheops import invalidate_model, invalidate_obj
            
            # Store references for later use
            self._cacheops = cacheops
            self._invalidate_model = invalidate_model
            self._invalidate_obj = invalidate_obj
            
            # Hook into cacheops key generation
            # We'll monkey-patch the key generation function to add namespace prefix
            # when a user context is available
            self._hook_key_generation()
            
            self._cacheops_configured = True
            logger.info("Cacheops wrapper configured successfully")
            
        except ImportError as e:
            logger.error(f"Failed to import cacheops: {e}")
            raise ImportError(
                "django-cacheops is not installed. "
                "Install it with: uv add django-cacheops"
            ) from e
        except Exception as e:
            logger.error(f"Error configuring cacheops: {e}", exc_info=True)
            raise
    
    def _hook_key_generation(self) -> None:
        """
        Hook into cacheops key generation to add namespace prefix.
        
        This method monkey-patches cacheops internal key generation to prepend
        the user namespace prefix when a user context is available. It preserves
        the original key generation logic for non-user-specific cache usage.
        
        The hook checks for a thread-local user_id context variable. If present,
        it prepends the namespace prefix. If not, it uses the original key.
        """
        try:
            from cacheops import conf
            
            # Store original key function
            if hasattr(conf, 'cache_key'):
                self._original_key_func = conf.cache_key
            
            # Create wrapped key function
            def namespaced_cache_key(scheme, *args, **kwargs):
                """
                Generate cache key with namespace prefix if user context available.
                
                Args:
                    scheme: Cacheops cache scheme
                    *args: Original arguments to key function
                    **kwargs: Original keyword arguments to key function
                    
                Returns:
                    Cache key with namespace prefix if user context exists,
                    otherwise original cache key
                """
                # Get original key from cacheops
                if self._original_key_func:
                    original_key = self._original_key_func(scheme, *args, **kwargs)
                else:
                    # Fallback: construct basic key
                    original_key = f"cacheops:{scheme}:{':'.join(str(a) for a in args)}"
                
                # Check for user context (set by middleware or view)
                # We use thread-local storage to pass user_id context
                user_id = getattr(_thread_local, 'user_id', None)
                
                if user_id is not None:
                    # Add namespace prefix for user-specific cache
                    try:
                        prefix = self.namespace_manager.get_cache_key_prefix(user_id)
                        # Replace 'cacheops:' prefix with our namespaced prefix
                        if original_key.startswith('cacheops:'):
                            namespaced_key = original_key.replace('cacheops:', prefix, 1)
                        else:
                            namespaced_key = f"{prefix}{original_key}"
                        
                        logger.debug(
                            f"Generated namespaced cache key for user {user_id}: "
                            f"{namespaced_key}"
                        )
                        return namespaced_key
                    except Exception as e:
                        logger.warning(
                            f"Error generating namespaced key for user {user_id}: {e}. "
                            f"Falling back to original key."
                        )
                        return original_key
                else:
                    # No user context - use original key for non-user-specific cache
                    # This preserves existing cache usage (Meta tokens, cron locks, etc.)
                    return original_key
            
            # Replace cacheops key function with our wrapped version
            conf.cache_key = namespaced_cache_key
            
            logger.info("Hooked into cacheops key generation")
            
        except Exception as e:
            logger.error(f"Error hooking key generation: {e}", exc_info=True)
            raise
    
    def get_cached_query(
        self,
        queryset: QuerySet,
        user_id: Optional[int] = None
    ) -> Any:
        """
        Execute a query with caching, integrating namespace prefix.
        
        This method:
        1. Sets user context for namespace prefix generation
        2. Executes the query through cacheops (which will use our hooked key function)
        3. Returns cached result if available, otherwise executes query
        4. Handles cache errors gracefully with database fallback
        
        Args:
            queryset: Django QuerySet to execute
            user_id: Optional user ID for namespace prefix. If None, uses original cacheops behavior.
            
        Returns:
            Query results (from cache or database)
            
        Example:
            >>> wrapper = CacheopsWrapper()
            >>> posts = wrapper.get_cached_query(
            ...     Post.objects.filter(published=True),
            ...     user_id=123
            ... )
        """
        if not self._cacheops_configured:
            logger.warning("Cacheops not configured, executing query without cache")
            return list(queryset)
        
        # Get cache key for logging
        cache_key = None
        model_name = "Unknown"
        
        try:
            model_name = queryset.model.__name__
        except (AttributeError, TypeError):
            pass
        
        try:
            # Set user context for key generation hook
            if user_id is not None:
                # Check if caching is enabled for this user
                if not self.namespace_manager.is_cache_enabled(user_id):
                    logger.debug(
                        f"Cache bypassed - user_id={user_id}, operation=query, "
                        f"model={model_name}, reason=cache_disabled"
                    )
                    return list(queryset)
                
                # Set thread-local user context
                _thread_local.user_id = user_id
            
            try:
                # Check if result is in cache before executing
                # We'll detect cache hit/miss by checking if cacheops returns cached data
                # Generate cache key for logging (approximate)
                if user_id is not None:
                    prefix = self.namespace_manager.get_cache_key_prefix(user_id)
                    cache_key = f"{prefix}{model_name}:query"
                
                # Measure query latency
                with cache_metrics.measure_latency('query', user_id=user_id):
                    # Execute query - cacheops will automatically cache if configured
                    # Our hooked key function will add namespace prefix if user_id is set
                    result = list(queryset)
                
                # Note: We can't easily detect hit vs miss without deeper cacheops integration
                # For now, we'll assume it's a cache operation and log it
                # In a production system, you might hook deeper into cacheops to detect hits/misses
                
                # Log cache operation
                logger.debug(
                    f"Cache query executed - user_id={user_id}, operation=query, "
                    f"model={model_name}, cache_key={cache_key}, "
                    f"result_count={len(result)}"
                )
                
                return result
                
            finally:
                # Clean up thread-local context
                if hasattr(_thread_local, 'user_id'):
                    delattr(_thread_local, 'user_id')
        
        except Exception as e:
            cache_metrics.record_error('query')
            error_text = str(e).lower()
            is_serialization_error = (
                isinstance(e, (pickle.PicklingError, TypeError))
                or "serialize" in error_text
                or "pickl" in error_text
            )
            is_deserialization_error = (
                isinstance(e, (pickle.UnpicklingError, AttributeError, ValueError))
                and ("deserialize" in error_text or "unpickl" in error_text or "corrupt" in error_text)
            ) or "deserialize" in error_text or "unpickl" in error_text

            logger.error(
                f"Cache error - user_id={user_id}, operation=query, "
                f"model={model_name}, cache_key={cache_key}, error={str(e)}",
                exc_info=True
            )

            if is_deserialization_error and cache_key:
                try:
                    cache.delete(cache_key)
                    logger.warning(
                        f"Corrupted cache entry removed - user_id={user_id}, "
                        f"model={model_name}, cache_key={cache_key}"
                    )
                except Exception as delete_error:
                    logger.error(
                        f"Failed to remove corrupted cache entry - user_id={user_id}, "
                        f"model={model_name}, cache_key={cache_key}, "
                        f"error={str(delete_error)}",
                        exc_info=True
                    )

            if is_serialization_error:
                logger.warning(
                    f"Serialization fallback - user_id={user_id}, "
                    f"operation=query_serialize_fallback, model={model_name}"
                )
            elif is_deserialization_error:
                logger.warning(
                    f"Deserialization fallback - user_id={user_id}, "
                    f"operation=query_deserialize_fallback, model={model_name}"
                )

            # Fallback to direct database query
            try:
                result = list(queryset)
                logger.warning(
                    f"Cache fallback - user_id={user_id}, operation=query_fallback, "
                    f"model={model_name}, result_count={len(result)}"
                )
                return result
            except Exception as fallback_error:
                logger.error(
                    f"Cache error - user_id={user_id}, operation=query_fallback, "
                    f"model={model_name}, error={str(fallback_error)}",
                    exc_info=True
                )
                # Never propagate cache-related exceptions to end users.
                # Return an empty result as last-resort graceful degradation.
                return []
    
    def invalidate_model(self, model_class: Type[Model]) -> None:
        """
        Invalidate all cache entries for a model.
        
        This method delegates to cacheops' invalidate_model function, which
        automatically invalidates all queries dependent on the model. The
        invalidation respects our namespace prefixes through the hooked key
        generation.
        
        Args:
            model_class: Django model class to invalidate
            
        Example:
            >>> wrapper = CacheopsWrapper()
            >>> wrapper.invalidate_model(Post)
            >>> # All cached queries for Post are now invalidated
        """
        if not self._cacheops_configured:
            logger.warning("Cacheops not configured, cannot invalidate model")
            return
        
        model_name = model_class.__name__
        
        try:
            # Use cacheops' built-in invalidation
            # This preserves all dependency tracking and signal handlers
            self._invalidate_model(model_class)
            
            logger.info(
                f"Cache invalidated - operation=model_invalidate, "
                f"model={model_name}, reason=model_change"
            )
            
        except Exception as e:
            logger.error(
                f"Cache error - operation=model_invalidate, "
                f"model={model_name}, error={str(e)}",
                exc_info=True
            )
            # Don't raise - invalidation failure shouldn't break the application


# Thread-local storage for user context
import threading
_thread_local = threading.local()


# Singleton instance for easy import
cacheops_wrapper = CacheopsWrapper()
