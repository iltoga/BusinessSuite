"""Property-based tests for the Document Type Hooks registry system.

**Feature: document-type-hooks, Property 1: Hook Registry Round-Trip**
**Feature: document-type-hooks, Property 2: Lifecycle Signal Dispatch**

This module tests that the HookRegistry correctly stores and retrieves hooks
by their document_type_name, ensuring round-trip consistency, and that
lifecycle signals correctly dispatch to registered hooks.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from hypothesis import given, settings, strategies as st, assume
from hypothesis.extra.django import TestCase as HypothesisTestCase

from customer_applications.hooks.base import BaseDocumentTypeHook
from customer_applications.hooks.registry import HookRegistry, hook_registry
from customer_applications.hooks import signals  # noqa: F401 - Register signal handlers
from customer_applications.models import DocApplication, Document
from customers.models import Customer
from products.models import Product
from products.models.document_type import DocumentType


class StubHook(BaseDocumentTypeHook):
    """A concrete hook implementation for testing purposes."""

    def __init__(self, document_type_name: str):
        self.document_type_name = document_type_name


class TrackingHook(BaseDocumentTypeHook):
    """A hook that tracks which lifecycle methods were called."""

    def __init__(self, document_type_name: str):
        self.document_type_name = document_type_name
        self.calls = []

    def on_init(self, document):
        self.calls.append(("on_init", document))

    def on_pre_save(self, document, created):
        self.calls.append(("on_pre_save", document, created))

    def on_post_save(self, document, created):
        self.calls.append(("on_post_save", document, created))

    def on_pre_delete(self, document):
        self.calls.append(("on_pre_delete", document))

    def reset(self):
        self.calls = []

    def was_called(self, method_name):
        return any(call[0] == method_name for call in self.calls)


# Strategy for generating valid document type names
# Document type names should be non-empty strings with printable characters
document_type_name_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        whitelist_characters=" -_",
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip())  # Ensure non-whitespace-only strings


# Strategy for lifecycle operations
lifecycle_operation_strategy = st.sampled_from(["save_new", "save_existing", "delete"])


class TestHookRegistryRoundTrip(TestCase):
    """Property-based tests for Hook Registry Round-Trip.

    **Feature: document-type-hooks, Property 1: Hook Registry Round-Trip**
    **Validates: Requirements 1.2, 1.3**

    Property: For any document type hook, registering it with the HookRegistry
    and then looking it up by document_type_name should return the same hook
    instance, and looking up an unregistered name should return None.
    """

    def setUp(self):
        """Create a fresh registry for each test."""
        self.registry = HookRegistry()
        self.registry.clear()

    @given(document_type_name=document_type_name_strategy)
    @settings(max_examples=100)
    def test_registered_hook_can_be_retrieved(self, document_type_name: str):
        """
        **Feature: document-type-hooks, Property 1: Hook Registry Round-Trip**
        **Validates: Requirements 1.2, 1.3**

        For any valid document_type_name, registering a hook and then
        retrieving it should return the exact same hook instance.
        """
        # Arrange
        self.registry.clear()
        hook = StubHook(document_type_name)

        # Act
        self.registry.register(hook)
        retrieved_hook = self.registry.get_hook(document_type_name)

        # Assert - Round-trip: registered hook should be retrievable
        self.assertIs(retrieved_hook, hook,
            f"Expected to retrieve the same hook instance for '{document_type_name}'"
        )

    @given(document_type_name=document_type_name_strategy)
    @settings(max_examples=100)
    def test_unregistered_hook_returns_none(self, document_type_name: str):
        """
        **Feature: document-type-hooks, Property 1: Hook Registry Round-Trip**
        **Validates: Requirements 1.3**

        For any document_type_name that has not been registered,
        get_hook should return None.
        """
        # Arrange - ensure registry is empty
        self.registry.clear()

        # Act
        retrieved_hook = self.registry.get_hook(document_type_name)

        # Assert - Unregistered names should return None
        self.assertIsNone(retrieved_hook,
            f"Expected None for unregistered document type '{document_type_name}'"
        )

    @given(
        name1=document_type_name_strategy,
        name2=document_type_name_strategy,
    )
    @settings(max_examples=100)
    def test_multiple_hooks_independent_retrieval(self, name1: str, name2: str):
        """
        **Feature: document-type-hooks, Property 1: Hook Registry Round-Trip**
        **Validates: Requirements 1.2, 1.3**

        For any two distinct document_type_names, registering hooks for both
        should allow independent retrieval of each hook.
        """
        # Skip if names are the same (different property)
        assume(name1 != name2)

        # Arrange
        self.registry.clear()
        hook1 = StubHook(name1)
        hook2 = StubHook(name2)

        # Act
        self.registry.register(hook1)
        self.registry.register(hook2)

        # Assert - Each hook should be retrievable independently
        self.assertIs(self.registry.get_hook(name1), hook1)
        self.assertIs(self.registry.get_hook(name2), hook2)


class TestLifecycleSignalDispatch(HypothesisTestCase):
    """Property-based tests for Lifecycle Signal Dispatch.

    **Feature: document-type-hooks, Property 2: Lifecycle Signal Dispatch**
    **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

    Property: For any Document instance with a doc_type that has a registered hook,
    the corresponding hook lifecycle method (on_init, on_pre_save, on_post_save,
    on_pre_delete) should be invoked when the respective Django signal fires.
    """

    def setUp(self):
        """Set up test fixtures."""
        import uuid
        User = get_user_model()

        # Store hook_registry reference for use in tests
        self.hook_registry = hook_registry
        self.hook_registry.clear()

        # Use unique identifiers to avoid conflicts between test runs
        unique_id = uuid.uuid4().hex[:8]

        # Create test user (get_or_create to handle existing data)
        self.user, _ = User.objects.get_or_create(
            username=f"testuser_lifecycle_{unique_id}",
            defaults={
                "email": f"test_lifecycle_{unique_id}@example.com",
                "password": "testpass123",
            }
        )

        # Create test customer (no created_by field on Customer model)
        self.customer, _ = Customer.objects.get_or_create(
            email=f"customer_lifecycle_{unique_id}@example.com",
            defaults={
                "first_name": "Test",
                "last_name": "Customer",
            }
        )

        # Create test product (no created_by field on Product model)
        self.product, _ = Product.objects.get_or_create(
            code=f"TESTLC{unique_id}",
            defaults={
                "name": "Test Product Lifecycle",
                "product_type": "other",
            }
        )

        # Create test document type with a unique name for this test
        self.doc_type_name = f"TestLifecycleDocType_{unique_id}"
        self.doc_type, _ = DocumentType.objects.get_or_create(
            name=self.doc_type_name,
            defaults={
                "has_file": False,
                "has_details": True,
            }
        )

        # Create test doc application
        self.doc_application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

        # Create and register tracking hook
        self.tracking_hook = TrackingHook(self.doc_type_name)
        self.hook_registry.register(self.tracking_hook)

    def tearDown(self):
        """Clean up after each test."""
        self.hook_registry.clear()

    @given(operation=lifecycle_operation_strategy)
    @settings(max_examples=100)
    def test_lifecycle_signals_dispatch_to_hook(self, operation: str):
        """
        **Feature: document-type-hooks, Property 2: Lifecycle Signal Dispatch**
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

        For any lifecycle operation (save new, save existing, delete) on a Document
        with a registered hook, the corresponding hook methods should be invoked.
        """
        # Reset tracking hook for this iteration
        self.tracking_hook.reset()

        if operation == "save_new":
            # Test on_pre_save and on_post_save for new document (Requirements 4.1, 4.2)
            document = Document(
                doc_application=self.doc_application,
                doc_type=self.doc_type,
                created_by=self.user,
            )
            document.save()

            # Verify pre_save was called with created=True
            pre_save_calls = [c for c in self.tracking_hook.calls if c[0] == "on_pre_save"]
            assert len(pre_save_calls) >= 1, "on_pre_save should be called for new document"
            assert pre_save_calls[0][2] is True, "created should be True for new document"

            # Verify post_save was called with created=True
            post_save_calls = [c for c in self.tracking_hook.calls if c[0] == "on_post_save"]
            assert len(post_save_calls) >= 1, "on_post_save should be called for new document"
            assert post_save_calls[0][2] is True, "created should be True for new document"

            # Clean up
            document.delete()

        elif operation == "save_existing":
            # First create a document
            document = Document(
                doc_application=self.doc_application,
                doc_type=self.doc_type,
                created_by=self.user,
            )
            document.save()

            # Reset tracking to only capture the update
            self.tracking_hook.reset()

            # Update the document (Requirements 4.1, 4.2)
            document.details = "Updated details"
            document.save()

            # Verify pre_save was called with created=False
            pre_save_calls = [c for c in self.tracking_hook.calls if c[0] == "on_pre_save"]
            assert len(pre_save_calls) >= 1, "on_pre_save should be called for existing document"
            assert pre_save_calls[0][2] is False, "created should be False for existing document"

            # Verify post_save was called with created=False
            post_save_calls = [c for c in self.tracking_hook.calls if c[0] == "on_post_save"]
            assert len(post_save_calls) >= 1, "on_post_save should be called for existing document"
            assert post_save_calls[0][2] is False, "created should be False for existing document"

            # Clean up
            document.delete()

        elif operation == "delete":
            # First create a document
            document = Document(
                doc_application=self.doc_application,
                doc_type=self.doc_type,
                created_by=self.user,
            )
            document.save()

            # Reset tracking to only capture the delete
            self.tracking_hook.reset()

            # Delete the document (Requirement 4.3)
            document.delete()

            # Verify pre_delete was called
            pre_delete_calls = [c for c in self.tracking_hook.calls if c[0] == "on_pre_delete"]
            assert len(pre_delete_calls) >= 1, "on_pre_delete should be called when deleting document"

    def test_no_hook_registered_no_error(self):
        """
        **Feature: document-type-hooks, Property 2: Lifecycle Signal Dispatch**
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

        When no hook is registered for a document type, lifecycle operations
        should complete without error (silent no-op).
        """
        # Create a document type without a registered hook
        unhooked_doc_type = DocumentType.objects.create(
            name="UnhookedDocType",
            has_file=False,
            has_details=True,
        )

        # Clear registry to ensure no hooks
        self.hook_registry.clear()

        # These operations should not raise any errors
        document = Document(
            doc_application=self.doc_application,
            doc_type=unhooked_doc_type,
            created_by=self.user,
        )
        document.save()  # Should not raise
        document.details = "Updated"
        document.save()  # Should not raise
        document.delete()  # Should not raise

    @given(doc_type_name=document_type_name_strategy)
    @settings(max_examples=100)
    def test_hook_receives_correct_document_instance(self, doc_type_name: str):
        """
        **Feature: document-type-hooks, Property 2: Lifecycle Signal Dispatch**
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

        For any document type name, when a hook is registered and a document
        is saved, the hook should receive the correct document instance.
        """
        # Skip if doc_type_name conflicts with existing types
        if DocumentType.objects.filter(name=doc_type_name).exists():
            assume(False)

        # Create document type with generated name
        doc_type = DocumentType.objects.create(
            name=doc_type_name,
            has_file=False,
            has_details=True,
        )

        # Create and register tracking hook
        tracking_hook = TrackingHook(doc_type_name)
        self.hook_registry.register(tracking_hook)

        try:
            # Create document
            document = Document(
                doc_application=self.doc_application,
                doc_type=doc_type,
                created_by=self.user,
            )
            document.save()

            # Verify the hook received the correct document instance
            pre_save_calls = [c for c in tracking_hook.calls if c[0] == "on_pre_save"]
            assert len(pre_save_calls) >= 1, "on_pre_save should be called"

            # The document passed to the hook should be the same instance
            received_doc = pre_save_calls[0][1]
            assert received_doc.doc_type.name == doc_type_name, (
                f"Hook should receive document with doc_type '{doc_type_name}'"
            )

            # Clean up
            document.delete()
        finally:
            # Clean up document type
            doc_type.delete()
