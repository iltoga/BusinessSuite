"""API endpoint for executing document type hook actions."""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import JsonResponse
from django.views import View

from customer_applications.hooks.registry import hook_registry
from customer_applications.models import Document

logger = logging.getLogger(__name__)


class DocumentActionView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """API endpoint for executing document type hook actions.

    Handles POST requests to execute named actions on documents via their
    registered hooks.
    """

    permission_required = ("customer_applications.change_document",)

    def post(self, request, document_id, action_name):
        """Execute a named action on a document.

        Args:
            request: The HTTP request object.
            document_id: The ID of the document to act on.
            action_name: The name of the action to execute.

        Returns:
            JsonResponse with success status and message or error.
        """
        try:
            document = Document.objects.select_related(
                "doc_type", "doc_application__customer"
            ).get(pk=document_id)
        except Document.DoesNotExist:
            logger.warning(
                "Document action requested for non-existent document: %s",
                document_id,
            )
            return JsonResponse(
                {"success": False, "error": "Document not found"},
                status=404,
            )

        hook = hook_registry.get_hook(document.doc_type.name)
        if not hook:
            logger.warning(
                "Document action requested but no hook registered for type: %s",
                document.doc_type.name,
            )
            return JsonResponse(
                {"success": False, "error": "No hook registered for this document type"},
                status=400,
            )

        # Verify the action exists for this hook
        available_actions = [action.name for action in hook.get_extra_actions()]
        if action_name not in available_actions:
            logger.warning(
                "Unknown action '%s' requested for document type '%s'",
                action_name,
                document.doc_type.name,
            )
            return JsonResponse(
                {"success": False, "error": f"Unknown action: {action_name}"},
                status=400,
            )

        result = hook.execute_action(action_name, document, request)

        if result.get("success"):
            logger.info(
                "Successfully executed action '%s' on document %s",
                action_name,
                document_id,
            )
        else:
            logger.error(
                "Failed to execute action '%s' on document %s: %s",
                action_name,
                document_id,
                result.get("error"),
            )

        return JsonResponse(result)
