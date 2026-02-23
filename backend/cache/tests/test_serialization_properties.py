"""
Property-based tests for cache serialization.

Tests serialization round-trip property for Django models and QuerySets.
"""

import pytest
from django.contrib.auth import get_user_model
from hypothesis import given, settings
from hypothesis import strategies as st

from cache.serialization import (
    deserialize,
    deserialize_to_list,
    is_serializable,
    safe_deserialize,
    safe_serialize,
    serialize,
    serialize_queryset,
)

User = get_user_model()


@pytest.mark.django_db
class TestSerializationProperties:
    """Property-based tests for serialization."""
    
    @given(
        username=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'),
            min_codepoint=65, max_codepoint=122
        )),
        email_local=st.text(min_size=1, max_size=20, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'),
            min_codepoint=65, max_codepoint=122
        )),
    )
    @settings(max_examples=50, deadline=5000)
    def test_property_15_serialization_round_trip_single_model(self, username, email_local):
        """
        Feature: hybrid-cache-system, Property 15: Serialization round-trip
        
        For any cacheable Django object (model instance or QuerySet),
        serializing then deserializing shall produce an equivalent object
        with the same data.
        
        Validates: Requirements 14.1, 14.2, 14.3, 14.4
        
        This test focuses on single model instances.
        """
        # Create a user model instance
        email = f"{email_local}@example.com"
        user = User.objects.create_user(
            username=username,
            email=email,
            password="testpass123"
        )
        
        try:
            # Serialize the user
            serialized = serialize(user)
            
            # Verify serialization produced bytes
            assert isinstance(serialized, bytes), "Serialization should produce bytes"
            assert len(serialized) > 0, "Serialized data should not be empty"
            
            # Deserialize back to object
            deserialized = deserialize(serialized)
            
            # Verify deserialized object is equivalent
            assert deserialized is not None, "Deserialized object should not be None"
            assert isinstance(deserialized, User), "Deserialized object should be User instance"
            
            # Verify data integrity
            assert deserialized.id == user.id, "User ID should match"
            assert deserialized.username == user.username, "Username should match"
            assert deserialized.email == user.email, "Email should match"
            
            # Verify the deserialized object is usable
            assert deserialized.check_password("testpass123"), "Password should still work"
            
        finally:
            # Cleanup
            user.delete()
    
    @given(
        count=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=20, deadline=5000)
    def test_property_15_serialization_round_trip_queryset(self, count):
        """
        Feature: hybrid-cache-system, Property 15: Serialization round-trip
        
        For any QuerySet, serializing then deserializing shall produce
        an equivalent list with the same data.
        
        Validates: Requirements 14.1, 14.2, 14.3, 14.4
        
        This test focuses on QuerySets with varying sizes.
        """
        # Create multiple users
        users = []
        for i in range(count):
            user = User.objects.create_user(
                username=f"user_{i}_{count}",
                email=f"user{i}@example.com",
                password="testpass123"
            )
            users.append(user)
        
        try:
            # Get QuerySet
            queryset = User.objects.filter(username__startswith=f"user_")
            
            # Serialize the QuerySet
            serialized = serialize_queryset(queryset)
            
            # Verify serialization produced bytes
            assert isinstance(serialized, bytes), "Serialization should produce bytes"
            
            # Deserialize back to list
            deserialized = deserialize_to_list(serialized)
            
            # Verify deserialized list
            assert isinstance(deserialized, list), "Deserialized should be a list"
            assert len(deserialized) == count, f"Should have {count} objects"
            
            # Verify each object
            for i, user_obj in enumerate(deserialized):
                assert isinstance(user_obj, User), "Each item should be User instance"
                assert user_obj.username.startswith("user_"), "Username should match pattern"
                
            # Verify data integrity for non-empty QuerySets
            if count > 0:
                # Check first user
                first_user = deserialized[0]
                assert first_user.id is not None, "User should have ID"
                assert first_user.username is not None, "User should have username"
                assert first_user.email is not None, "User should have email"
        
        finally:
            # Cleanup
            for user in users:
                user.delete()
    
    @given(
        value=st.one_of(
            st.none(),
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(max_size=100),
            st.booleans(),
            st.lists(st.integers(), max_size=10),
            st.dictionaries(st.text(max_size=10), st.integers(), max_size=5),
        )
    )
    @settings(max_examples=50, deadline=5000)
    def test_property_15_serialization_round_trip_basic_types(self, value):
        """
        Feature: hybrid-cache-system, Property 15: Serialization round-trip
        
        For any basic Python type, serializing then deserializing shall
        produce an equivalent value.
        
        Validates: Requirements 14.1, 14.2, 14.3, 14.4
        
        This test focuses on basic Python types (None, int, str, list, dict).
        """
        # Serialize the value
        serialized = serialize(value)
        
        # Verify serialization produced bytes
        assert isinstance(serialized, bytes), "Serialization should produce bytes"
        
        # Deserialize back to value
        deserialized = deserialize(serialized)
        
        # Verify equivalence
        assert deserialized == value, f"Deserialized value should equal original: {value}"
        assert type(deserialized) == type(value), "Type should be preserved"
    
    def test_empty_queryset_serialization(self):
        """Test that empty QuerySets serialize and deserialize correctly."""
        # Get empty QuerySet
        queryset = User.objects.filter(username="nonexistent_user_xyz")
        
        # Serialize
        serialized = serialize_queryset(queryset)
        
        # Deserialize
        deserialized = deserialize_to_list(serialized)
        
        # Verify
        assert isinstance(deserialized, list), "Should be a list"
        assert len(deserialized) == 0, "Should be empty"
    
    def test_none_serialization(self):
        """Test that None serializes and deserializes correctly."""
        # Serialize None
        serialized = serialize(None)
        
        # Deserialize
        deserialized = deserialize(serialized)
        
        # Verify
        assert deserialized is None, "Should be None"
    
    def test_is_serializable_utility(self):
        """Test the is_serializable utility function."""
        # Create a user
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        try:
            # Test serializable objects
            assert is_serializable(user) is True, "User should be serializable"
            assert is_serializable([user]) is True, "List of users should be serializable"
            assert is_serializable(None) is True, "None should be serializable"
            assert is_serializable("test") is True, "String should be serializable"
            assert is_serializable(123) is True, "Integer should be serializable"
            assert is_serializable([1, 2, 3]) is True, "List should be serializable"
            assert is_serializable({"key": "value"}) is True, "Dict should be serializable"
            
        finally:
            user.delete()
    
    def test_safe_serialize_utility(self):
        """Test the safe_serialize utility function."""
        # Create a user
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        try:
            # Test safe serialization
            serialized = safe_serialize(user)
            assert serialized is not None, "Should serialize successfully"
            assert isinstance(serialized, bytes), "Should return bytes"
            
            # Test with default value
            serialized = safe_serialize(user, default=b"default")
            assert serialized is not None, "Should serialize successfully"
            
        finally:
            user.delete()
    
    def test_safe_deserialize_utility(self):
        """Test the safe_deserialize utility function."""
        # Create a user
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        try:
            # Serialize
            serialized = serialize(user)
            
            # Test safe deserialization
            deserialized = safe_deserialize(serialized)
            assert deserialized is not None, "Should deserialize successfully"
            assert isinstance(deserialized, User), "Should be User instance"
            
            # Test with corrupted data
            corrupted = b"corrupted data"
            deserialized = safe_deserialize(corrupted, default="default")
            assert deserialized == "default", "Should return default on failure"
            
        finally:
            user.delete()
    
    def test_deserialize_to_list_utility(self):
        """Test the deserialize_to_list utility function."""
        # Create users
        user1 = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            password="testpass123"
        )
        user2 = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="testpass123"
        )
        
        try:
            # Test with list
            serialized = serialize([user1, user2])
            deserialized = deserialize_to_list(serialized)
            assert isinstance(deserialized, list), "Should be list"
            assert len(deserialized) == 2, "Should have 2 items"
            
            # Test with single object
            serialized = serialize(user1)
            deserialized = deserialize_to_list(serialized)
            assert isinstance(deserialized, list), "Should be list"
            assert len(deserialized) == 1, "Should have 1 item"
            
            # Test with None
            serialized = serialize(None)
            deserialized = deserialize_to_list(serialized)
            assert isinstance(deserialized, list), "Should be list"
            assert len(deserialized) == 0, "Should be empty"
            
        finally:
            user1.delete()
            user2.delete()
