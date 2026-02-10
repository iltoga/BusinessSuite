"""Central registry for document type hooks."""

from typing import Dict, Optional

from .base import BaseDocumentTypeHook


class HookRegistry:
    """Central registry for document type hooks.

    This is implemented as a singleton to ensure a single registry
    instance across the application.
    """

    _instance: Optional["HookRegistry"] = None
    _hooks: Dict[str, BaseDocumentTypeHook]

    def __new__(cls) -> "HookRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._hooks = {}
        return cls._instance

    def register(self, hook: BaseDocumentTypeHook) -> None:
        """Register a hook for a document type.

        Args:
            hook: The hook instance to register. Must have document_type_name set.
        """
        if not hook.document_type_name:
            raise ValueError("Hook must have document_type_name set")
        self._hooks[hook.document_type_name] = hook

    def get_hook(self, document_type_name: str) -> Optional[BaseDocumentTypeHook]:
        """Get the hook for a document type, or None if not registered.

        This method will attempt to lazily import the package-level hooks
        (``customer_applications.hooks``) if the requested hook is not found.
        This keeps tests and runtime behaviour stable even when tests clear
        the registry for isolation.

        Args:
            document_type_name: The name of the document type.

        Returns:
            The registered hook instance, or None if no hook is registered.
        """
        hook = self._hooks.get(document_type_name)
        if hook is None:
            # Attempt to lazily load package-level hook registrations
            try:
                import importlib

                importlib.import_module("customer_applications.hooks")
            except Exception:
                pass
            # Return after attempting registration
            return self._hooks.get(document_type_name)
        return hook

    def get_all_hooks(self) -> Dict[str, BaseDocumentTypeHook]:
        """Return a copy of all registered hooks."""
        return self._hooks.copy()

    def clear(self) -> None:
        """Clear all registered hooks. Useful for testing."""
        self._hooks = {}


# Global registry instance
hook_registry = HookRegistry()

# Ensure package-level hook registrations are executed when registry is imported directly
try:
    import importlib

    importlib.import_module("customer_applications.hooks")
except Exception:
    # Best-effort: ignore import errors during early test runs
    pass
