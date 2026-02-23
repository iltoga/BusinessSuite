"""
Cache serialization utilities for Django models and QuerySets.

Provides functions to serialize and deserialize Django objects for cache storage.
Handles edge cases like empty QuerySets, None values, and serialization failures.
"""

import logging
import pickle
from typing import Any, List, Optional, Union

from django.db.models import Model, QuerySet

logger = logging.getLogger(__name__)


def serialize(obj: Any) -> bytes:
    """
    Serialize a Django object for cache storage.
    
    Supports:
    - Django model instances
    - Django QuerySets
    - Lists of model instances
    - None values
    - Basic Python types (str, int, dict, list, etc.)
    
    Args:
        obj: Object to serialize
        
    Returns:
        Serialized bytes suitable for Redis storage
        
    Raises:
        ValueError: If object cannot be serialized
        
    Example:
        >>> post = Post.objects.get(id=1)
        >>> serialized = serialize(post)
        >>> # Store in Redis
        >>> cache.set(key, serialized)
    """
    try:
        # Handle None
        if obj is None:
            return pickle.dumps(None)
        
        # Handle QuerySet - convert to list first
        if isinstance(obj, QuerySet):
            # Evaluate QuerySet to list of model instances
            obj_list = list(obj)
            logger.debug(f"Serializing QuerySet with {len(obj_list)} objects")
            return pickle.dumps(obj_list)
        
        # Handle list of model instances
        if isinstance(obj, list):
            if obj and isinstance(obj[0], Model):
                logger.debug(f"Serializing list of {len(obj)} model instances")
            return pickle.dumps(obj)
        
        # Handle single model instance
        if isinstance(obj, Model):
            logger.debug(f"Serializing model instance: {obj.__class__.__name__}")
            return pickle.dumps(obj)
        
        # Handle other types (str, int, dict, etc.)
        return pickle.dumps(obj)
        
    except Exception as e:
        logger.error(f"Serialization error for {type(obj).__name__}: {e}", exc_info=True)
        raise ValueError(f"Failed to serialize object of type {type(obj).__name__}: {e}") from e


def deserialize(data: bytes) -> Any:
    """
    Deserialize cached data back to original Python objects.
    
    Handles:
    - Django model instances
    - Lists of model instances
    - None values
    - Basic Python types
    
    Args:
        data: Serialized bytes from cache
        
    Returns:
        Deserialized Python object
        
    Raises:
        ValueError: If data cannot be deserialized
        
    Example:
        >>> serialized = cache.get(key)
        >>> post = deserialize(serialized)
        >>> print(post.title)
    """
    try:
        # Handle None or empty data
        if data is None:
            return None
        
        if not data:
            logger.warning("Attempting to deserialize empty data")
            return None
        
        # Deserialize using pickle
        obj = pickle.loads(data)
        
        # Log what we deserialized
        if obj is None:
            logger.debug("Deserialized None value")
        elif isinstance(obj, list):
            if obj and isinstance(obj[0], Model):
                logger.debug(f"Deserialized list of {len(obj)} model instances")
            else:
                logger.debug(f"Deserialized list with {len(obj)} items")
        elif isinstance(obj, Model):
            logger.debug(f"Deserialized model instance: {obj.__class__.__name__}")
        else:
            logger.debug(f"Deserialized {type(obj).__name__}")
        
        return obj
        
    except pickle.UnpicklingError as e:
        logger.error(f"Unpickling error: {e}", exc_info=True)
        raise ValueError(f"Failed to deserialize data: corrupted pickle data") from e
    except AttributeError as e:
        logger.error(f"Attribute error during deserialization: {e}", exc_info=True)
        raise ValueError(
            f"Failed to deserialize data: model structure may have changed"
        ) from e
    except Exception as e:
        logger.error(f"Deserialization error: {e}", exc_info=True)
        raise ValueError(f"Failed to deserialize data: {e}") from e


def serialize_queryset(queryset: QuerySet) -> bytes:
    """
    Serialize a Django QuerySet for cache storage.
    
    This is a convenience function that explicitly handles QuerySets.
    It evaluates the QuerySet and serializes the resulting list.
    
    Args:
        queryset: Django QuerySet to serialize
        
    Returns:
        Serialized bytes
        
    Raises:
        ValueError: If QuerySet cannot be serialized
        
    Example:
        >>> posts = Post.objects.filter(published=True)
        >>> serialized = serialize_queryset(posts)
    """
    try:
        # Evaluate QuerySet to list
        obj_list = list(queryset)
        
        # Handle empty QuerySet
        if not obj_list:
            logger.debug("Serializing empty QuerySet")
            return pickle.dumps([])
        
        logger.debug(
            f"Serializing QuerySet of {queryset.model.__name__} "
            f"with {len(obj_list)} objects"
        )
        
        return pickle.dumps(obj_list)
        
    except Exception as e:
        logger.error(
            f"Error serializing QuerySet of {queryset.model.__name__}: {e}",
            exc_info=True
        )
        raise ValueError(f"Failed to serialize QuerySet: {e}") from e


def deserialize_to_list(data: bytes) -> List[Model]:
    """
    Deserialize cached data to a list of model instances.
    
    This is a convenience function that ensures the result is a list,
    even if the cached data was a single object or None.
    
    Args:
        data: Serialized bytes from cache
        
    Returns:
        List of model instances (empty list if None)
        
    Raises:
        ValueError: If data cannot be deserialized
        
    Example:
        >>> serialized = cache.get(key)
        >>> posts = deserialize_to_list(serialized)
        >>> for post in posts:
        ...     print(post.title)
    """
    try:
        obj = deserialize(data)
        
        # Handle None
        if obj is None:
            return []
        
        # Handle list
        if isinstance(obj, list):
            return obj
        
        # Handle single object - wrap in list
        return [obj]
        
    except Exception as e:
        logger.error(f"Error deserializing to list: {e}", exc_info=True)
        raise


def is_serializable(obj: Any) -> bool:
    """
    Check if an object can be serialized.
    
    This is a utility function to test if an object can be safely
    serialized before attempting to cache it.
    
    Args:
        obj: Object to test
        
    Returns:
        True if object can be serialized, False otherwise
        
    Example:
        >>> post = Post.objects.get(id=1)
        >>> if is_serializable(post):
        ...     cache.set(key, serialize(post))
    """
    try:
        serialize(obj)
        return True
    except Exception:
        return False


def safe_serialize(obj: Any, default: Optional[bytes] = None) -> Optional[bytes]:
    """
    Safely serialize an object, returning default value on failure.
    
    This is a convenience function that doesn't raise exceptions,
    making it suitable for use in contexts where serialization
    failure should be handled gracefully.
    
    Args:
        obj: Object to serialize
        default: Value to return on failure (default: None)
        
    Returns:
        Serialized bytes or default value
        
    Example:
        >>> post = Post.objects.get(id=1)
        >>> serialized = safe_serialize(post)
        >>> if serialized:
        ...     cache.set(key, serialized)
    """
    try:
        return serialize(obj)
    except Exception as e:
        logger.warning(f"Safe serialization failed for {type(obj).__name__}: {e}")
        return default


def safe_deserialize(data: bytes, default: Any = None) -> Any:
    """
    Safely deserialize data, returning default value on failure.
    
    This is a convenience function that doesn't raise exceptions,
    making it suitable for use in contexts where deserialization
    failure should be handled gracefully.
    
    Args:
        data: Serialized bytes from cache
        default: Value to return on failure (default: None)
        
    Returns:
        Deserialized object or default value
        
    Example:
        >>> serialized = cache.get(key)
        >>> post = safe_deserialize(serialized)
        >>> if post:
        ...     print(post.title)
    """
    try:
        return deserialize(data)
    except Exception as e:
        logger.warning(f"Safe deserialization failed: {e}")
        return default
