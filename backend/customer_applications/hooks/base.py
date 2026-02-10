"""Base classes for document type hooks."""

from abc import ABC
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from django.http import HttpRequest
    from customer_applications.models import Document


class DocumentAction:
    """Represents a UI action for a document type."""

    def __init__(
        self,
        name: str,
        label: str,
        icon: str = "",
        css_class: str = "btn-secondary",
    ):
        self.name = name
        self.label = label
        self.icon = icon
        self.css_class = css_class

    def __repr__(self) -> str:
        return f"DocumentAction(name={self.name!r}, label={self.label!r})"


class BaseDocumentTypeHook(ABC):
    """Base class for document type hooks.

    Subclasses should set document_type_name and override lifecycle methods
    as needed for document-type-specific behavior.
    """

    document_type_name: str = ""

    def on_init(self, document: "Document") -> None:
        """Called when a Document instance is initialized."""
        pass

    def on_pre_save(self, document: "Document", created: bool) -> None:
        """Called before a Document is saved.

        Args:
            document: The Document instance being saved.
            created: True if this is a new document (pk is None).
        """
        pass

    def on_post_save(self, document: "Document", created: bool) -> None:
        """Called after a Document is saved.

        Args:
            document: The Document instance that was saved.
            created: True if this was a new document.
        """
        pass

    def on_pre_delete(self, document: "Document") -> None:
        """Called before a Document is deleted."""
        pass

    def get_default_values(self) -> Dict[str, Any]:
        """Returns default field values for this document type."""
        return {}

    def get_extra_actions(self) -> List[DocumentAction]:
        """Returns list of extra UI actions for this document type."""
        return []

    def execute_action(
        self, action_name: str, document: "Document", request: "HttpRequest"
    ) -> Dict[str, Any]:
        """Execute a named action and return result.

        Args:
            action_name: The name of the action to execute.
            document: The Document instance to act on.
            request: The HTTP request object.

        Returns:
            A dict with 'success' boolean and either 'message' or 'error'.
        """
        return {"success": False, "error": "Action not implemented"}
