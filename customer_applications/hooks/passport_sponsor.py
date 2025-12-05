"""Passport Sponsor document type hook.

This hook provides a custom action to upload a default sponsor passport file
to Passport Sponsor documents.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage

from .base import BaseDocumentTypeHook, DocumentAction

if TYPE_CHECKING:
    from django.http import HttpRequest

    from customer_applications.models import Document

logger = logging.getLogger(__name__)


class PassportSponsorHook(BaseDocumentTypeHook):
    """Hook for Passport Sponsor document type.

    Provides a custom action button to upload the default sponsor passport file
    from Django settings. Users can either click the button to use the default
    file or upload their own custom file.
    """

    document_type_name = "Passport Sponsor"

    def get_extra_actions(self) -> List[DocumentAction]:
        """Returns the upload default action if a default file is configured."""
        default_path = getattr(settings, "DEFAULT_SPONSOR_PASSPORT_FILE", None)
        if not default_path:
            return []

        if not default_storage.exists(default_path):
            logger.warning(
                "DEFAULT_SPONSOR_PASSPORT_FILE configured but file not found: %s",
                default_path,
            )
            return []

        return [
            DocumentAction(
                name="upload_default",
                label="Upload Default Sponsor Document",
                icon="fas fa-file-upload",
                css_class="btn-success",
            )
        ]

    def execute_action(self, action_name: str, document: "Document", request: "HttpRequest") -> Dict[str, Any]:
        """Execute a named action on the document.

        Args:
            action_name: The name of the action to execute.
            document: The Document instance to act on.
            request: The HTTP request object.

        Returns:
            A dict with 'success' boolean and either 'message' or 'error'.
        """
        if action_name == "upload_default":
            return self._upload_default_file(document)
        return {"success": False, "error": "Unknown action"}

    def _upload_default_file(self, document: "Document") -> Dict[str, Any]:
        """Upload the default sponsor passport file to the document.

        Args:
            document: The Document instance to upload the file to.

        Returns:
            A dict with 'success' boolean and either 'message' or 'error'.
        """
        default_path = getattr(settings, "DEFAULT_SPONSOR_PASSPORT_FILE", None)
        if not default_path:
            return {"success": False, "error": "No default sponsor file configured"}

        if not default_storage.exists(default_path):
            return {"success": False, "error": f"Default file not found: {default_path}"}

        try:
            with default_storage.open(default_path, "rb") as f:
                filename = default_path.split("/")[-1]
                document.file.save(filename, File(f), save=True)
                logger.info(
                    "Uploaded default sponsor passport file to document %s",
                    document.pk,
                )
            return {"success": True, "message": "Default sponsor document uploaded successfully"}
        except Exception as e:
            logger.error(
                "Failed to upload default sponsor passport file: %s",
                str(e),
            )
            return {"success": False, "error": str(e)}
