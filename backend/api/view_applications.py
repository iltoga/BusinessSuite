"""
api.view_applications
=====================
DRF ViewSet controllers for customer applications, documents, and OCR jobs.

``DocApplicationViewSet`` (ModelViewSet)
-----------------------------------------
Standard CRUD for ``DocApplication`` with additional custom actions:

- **list** — supports ``search`` / ``q`` query params and ``customer_id``
  filter; annotated with ``document_collection_completed`` flag.
- **retrieve** — includes nested documents and workflow steps.
- Permission: ``IsAuthenticated`` + ``DjangoModelPermissions``.

OCR job enqueueing
------------------
- **enqueue_ocr** (POST on a ``Document``) — validates the document file,
  creates an ``OCRJob`` record, and enqueues the actor on the
  ``doc_conversion`` queue.  Returns ``{job_id, status}``.
- **enqueue_document_ocr** (POST on a ``Document``) — same for
  ``DocumentOCRJob`` (text extraction / AI validation flow).

OCR status polling helpers
--------------------------
- ``_build_ocr_status_payload(job, request)`` — builds the JSON response for
  ``GET /ocr-jobs/{id}/status/``; injects a temporary ``preview_url`` from
  ``default_storage`` when the job is complete.
- ``_build_document_ocr_status_payload(job)`` — parallel helper for
  ``DocumentOCRJob``; parses ``result_text`` as JSON when possible.

Document completion auto-calculation
-------------------------------------
``Document.completed`` is computed inside ``Document.save()`` based on
``DocumentType.requires_verification`` and uploaded file / field presence.
Views must not set ``completed`` directly; they should update the underlying
fields (``doc_number``, ``expiration_date``, ``file``) and let the model
recalculate.

SSE stream payloads
-------------------
OCR progress is delivered via ``/api/async-jobs/status/{job_id}/``.  The
payload shape is normalised by ``normalize_ocr_job_payload()`` /
``normalize_document_ocr_job_payload()`` before being published to Redis
Streams.
"""

import logging

from api.utils.stream_payloads import (
    build_async_job_links,
    build_async_job_start_payload,
    normalize_document_ocr_job_payload,
    normalize_ocr_job_payload,
    normalize_ocr_result_payload,
)
from api.utils.contracts import build_error_payload, build_success_payload
from api.utils.idempotency import resolve_request_idempotent_job, store_request_idempotent_job

from .views_imports import *

logger = logging.getLogger(__name__)


def _build_ocr_status_payload(job: OCRJob, request) -> dict[str, Any]:
    response_data = {
        "jobId": str(job.id),
        "status": job.status,
        "progress": job.progress,
    }

    if job.status == OCRJob.STATUS_COMPLETED:
        if job.result:
            response_data.update(normalize_ocr_result_payload(job.result) or {})
        if job.save_session and not job.session_saved and job.result:
            request.session["file_path"] = job.file_path
            request.session["file_url"] = job.file_url
            request.session["mrz_data"] = job.result.get("mrz_data")
            request.session.save()
            job.session_saved = True
            job.save(update_fields=["session_saved", "updated_at"])
    elif job.status == OCRJob.STATUS_FAILED:
        response_data["errorMessage"] = job.error_message or "OCR job failed"

    return response_data


def _build_document_ocr_status_payload(job: DocumentOCRJob) -> dict[str, Any]:
    response_data = {
        "jobId": str(job.id),
        "status": job.status,
        "progress": job.progress,
    }

    if job.status == DocumentOCRJob.STATUS_COMPLETED:
        response_data["resultText"] = job.result_text
        try:
            structured_data = json.loads(job.result_text or "")
        except (TypeError, ValueError, json.JSONDecodeError):
            structured_data = None
        if isinstance(structured_data, dict):
            response_data["structuredData"] = normalize_ocr_result_payload(
                {"structuredData": structured_data}
            )["structuredData"]
    elif job.status == DocumentOCRJob.STATUS_FAILED:
        response_data["errorMessage"] = job.error_message or "Document OCR job failed"

    return response_data


def _build_ocr_stream_payload(stream_payload: dict[str, Any]) -> dict[str, Any]:
    response_data = {
        "jobId": str(stream_payload["jobId"]),
        "status": stream_payload["status"],
        "progress": stream_payload["progress"],
    }
    error_message = stream_payload.get("errorMessage")
    if error_message:
        response_data["errorMessage"] = error_message
    return response_data


def _build_document_ocr_stream_payload(stream_payload: dict[str, Any]) -> dict[str, Any]:
    response_data = {
        "jobId": str(stream_payload["jobId"]),
        "status": stream_payload["status"],
        "progress": stream_payload["progress"],
    }
    error_message = stream_payload.get("errorMessage")
    if error_message:
        response_data["errorMessage"] = error_message
    return response_data


from api.serializers.doc_application_serializer import DocApplicationListSerializer


@extend_schema_view(list=extend_schema(responses={200: DocApplicationListSerializer(many=True)}))
class CustomerApplicationViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "product__name",
        "product__code",
        "customer__first_name",
        "customer__last_name",
        "doc_date",
    ]
    ordering = ["-id"]

    def get_queryset(self):
        queryset = (
            DocApplication.objects.select_related("customer", "product")
            .select_related(
                "customer__nationality",
                "product__created_by",
                "product__updated_by",
            )
            .prefetch_related(
                "product__tasks",
                Prefetch(
                    "documents",
                    queryset=Document.objects.select_related("doc_type", "created_by", "updated_by"),
                ),
                Prefetch(
                    "workflows",
                    queryset=DocWorkflow.objects.select_related("task", "created_by", "updated_by"),
                ),
                Prefetch(
                    "invoice_applications",
                    queryset=InvoiceApplication.objects.select_related("invoice"),
                ),
            )
        )

        if self.action == "list":
            queryset = queryset.filter(product__uses_customer_app_workflow=True)

        # Detail responses can derive completion state from prefetched documents,
        # so skip aggregate annotations to keep the base query lighter.
        if self.action != "retrieve":
            queryset = queryset.annotate(
                total_required_documents=Count("documents", filter=Q(documents__required=True)),
                completed_required_documents=Count(
                    "documents", filter=Q(documents__required=True, documents__completed=True)
                ),
            )

        return queryset

    def get_serializer_class(self):
        # Use specialized serializer for create/update actions
        if self.action in ["create", "update", "partial_update"]:
            from api.serializers.doc_application_serializer import DocApplicationCreateUpdateSerializer

            return DocApplicationCreateUpdateSerializer
        if self.action == "list":
            from api.serializers.doc_application_serializer import DocApplicationListSerializer

            return DocApplicationListSerializer
        if self.action == "retrieve":
            return DocApplicationDetailSerializer
        return DocApplicationSerializerWithRelations

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == "retrieve":
            # Avoid expensive per-document storage URL generation on detail load.
            context["prefer_cached_file_url"] = True
        return context

    def _serialize_application_detail(self, application):
        detail_instance = application
        if not self._can_serialize_application_without_refetch(application):
            detail_instance = (
                self.get_queryset().filter(pk=application.pk).first()
                if getattr(application, "pk", None)
                else application
            )
        return DocApplicationDetailSerializer(
            detail_instance or application,
            context={
                "request": self.request,
                "prefer_cached_file_url": True,
            },
        ).data

    def _can_serialize_application_without_refetch(self, application) -> bool:
        if not getattr(application, "pk", None):
            return False

        prefetched = getattr(application, "_prefetched_objects_cache", None) or {}
        if not {"documents", "workflows", "invoice_applications"}.issubset(prefetched.keys()):
            return False

        product = getattr(application, "product", None)
        customer = getattr(application, "customer", None)
        if product is None or customer is None:
            return False

        product_prefetched = getattr(product, "_prefetched_objects_cache", None) or {}
        return "tasks" in product_prefetched

    def _ensure_application_product_is_active(self, application):
        if application.product and application.product.deprecated:
            return self.error_response(
                "This application uses a deprecated product and workflow actions are disabled.",
                status.HTTP_409_CONFLICT,
            )
        return None

    def _queue_calendar_sync(
        self,
        *,
        application_id: int,
        user_id: int,
        previous_due_date=None,
        start_date=None,
    ):
        from customer_applications.tasks import SYNC_ACTION_UPSERT, sync_application_calendar_task

        previous_due_date_value = previous_due_date.isoformat() if previous_due_date else None
        start_date_value = start_date.isoformat() if start_date else None

        transaction.on_commit(
            lambda: sync_application_calendar_task(
                application_id=application_id,
                user_id=user_id,
                action=SYNC_ACTION_UPSERT,
                previous_due_date=previous_due_date_value,
                start_date=start_date_value,
            )
        )

    def _get_application_workflow_or_none(self, *, application_id: int, workflow_id: int):
        from customer_applications.models.doc_workflow import DocWorkflow

        return (
            DocWorkflow.objects.select_related("doc_application", "task")
            .filter(pk=workflow_id, doc_application_id=application_id)
            .first()
        )

    def _get_previous_workflow(self, workflow):
        return (
            workflow.doc_application.workflows.filter(task__step__lt=workflow.task.step)
            .order_by("-task__step", "-created_at", "-id")
            .first()
        )

    def _parse_request_date(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value)).date()
        except (TypeError, ValueError):
            return None

    @extend_schema(responses={201: DocApplicationDetailSerializer})
    def create(self, request, *args, **kwargs):
        """Create application synchronously and queue calendar sync in Dramatiq."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = serializer.save()
        self._queue_calendar_sync(application_id=application.id, user_id=request.user.id)
        data = self._serialize_application_detail(application)
        headers = self.get_success_headers(serializer.data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    @extend_schema(responses={200: DocApplicationDetailSerializer})
    def update(self, request, *args, **kwargs):
        """Update application synchronously and queue calendar sync in Dramatiq."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        previous_due_date = instance.due_date
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        application = serializer.save()
        self._queue_calendar_sync(
            application_id=application.id,
            user_id=request.user.id,
            previous_due_date=previous_due_date,
        )
        return Response(self._serialize_application_detail(application), status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        if not is_superuser(request.user):
            return self.error_response("You do not have permission to perform this action.", status.HTTP_403_FORBIDDEN)

        from core.services.bulk_delete import bulk_delete_applications

        query = (
            request.data.get("search_query") or request.data.get("searchQuery") or request.data.get("query") or ""
        ).strip()
        count = bulk_delete_applications(query=query or None)
        return Response(build_success_payload({"deletedCount": count}, request=request))

    @action(detail=True, methods=["post"], url_path="advance-workflow")
    @extend_schema(responses={200: DocApplicationDetailSerializer})
    def advance_workflow(self, request, pk=None):
        """Complete current workflow synchronously and queue calendar sync in Dramatiq."""
        from customer_applications.services.application_lifecycle_service import ApplicationLifecycleService

        try:
            application = self.get_object()
        except DocApplication.DoesNotExist:
            return self.error_response("Application not found", status.HTTP_404_NOT_FOUND)

        deprecated_response = self._ensure_application_product_is_active(application)
        if deprecated_response:
            return deprecated_response

        result = ApplicationLifecycleService().advance_workflow(application=application, user=request.user)
        self._queue_calendar_sync(
            application_id=result.application.id,
            user_id=request.user.id,
            previous_due_date=result.previous_due_date,
            start_date=result.start_date,
        )
        return Response(self._serialize_application_detail(result.application), status=status.HTTP_200_OK)

    @extend_schema(
        parameters=[
            OpenApiParameter("delete_invoices", OpenApiTypes.BOOL, OpenApiParameter.QUERY),
            OpenApiParameter("deleteInvoices", OpenApiTypes.BOOL, OpenApiParameter.QUERY),
        ],
        responses={204: OpenApiTypes.NONE},
    )
    def destroy(self, request, *args, **kwargs):
        """Delete application synchronously and queue calendar cleanup in Dramatiq."""
        from customer_applications.services.application_lifecycle_service import ApplicationLifecycleService

        try:
            application = self.get_object()
        except DocApplication.DoesNotExist:
            return self.error_response("Application not found", status.HTTP_404_NOT_FOUND)

        delete_invoices = parse_bool(
            request.data.get("deleteInvoices")
            or request.data.get("delete_with_invoices")
            or request.query_params.get("deleteInvoices")
            or request.query_params.get("delete_invoices")
        )

        ApplicationLifecycleService().delete_application(
            application=application,
            user=request.user,
            delete_invoices=delete_invoices,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses=DocWorkflowSerializer,
        parameters=[OpenApiParameter("workflow_id", OpenApiTypes.INT, OpenApiParameter.PATH)],
    )
    @action(detail=True, methods=["post"], url_path=r"workflows/(?P<workflow_id>[^/.]+)/status")
    def update_workflow_status(self, request, pk=None, workflow_id=None):
        """Update the status of a workflow step for an application."""
        from customer_applications.services.workflow_status_transition_service import (
            WorkflowStatusTransitionError,
            WorkflowStatusTransitionService,
        )

        status_value = request.data.get("status")
        valid_statuses = WorkflowStatusTransitionService.valid_statuses()

        if not status_value or status_value not in valid_statuses:
            return self.error_response("Invalid workflow status", status.HTTP_400_BAD_REQUEST)

        workflow = self._get_application_workflow_or_none(application_id=pk, workflow_id=workflow_id)
        if not workflow:
            return self.error_response("Workflow not found", status.HTTP_404_NOT_FOUND)

        deprecated_response = self._ensure_application_product_is_active(workflow.doc_application)
        if deprecated_response:
            return deprecated_response

        from api.serializers.doc_workflow_serializer import DocWorkflowSerializer

        if workflow.status == status_value:
            return Response(DocWorkflowSerializer(workflow).data)

        try:
            transition_result = WorkflowStatusTransitionService().transition(
                workflow=workflow,
                status_value=status_value,
                user=request.user,
            )
        except WorkflowStatusTransitionError as exc:
            return self.error_response(str(exc), status.HTTP_400_BAD_REQUEST)

        if transition_result.changed:
            self._queue_calendar_sync(
                application_id=transition_result.application.id,
                user_id=request.user.id,
                previous_due_date=transition_result.previous_due_date,
                start_date=transition_result.next_start_date,
            )

        return Response(DocWorkflowSerializer(workflow).data)

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses=DocWorkflowSerializer,
        parameters=[OpenApiParameter("workflow_id", OpenApiTypes.INT, OpenApiParameter.PATH)],
    )
    @action(detail=True, methods=["post"], url_path=r"workflows/(?P<workflow_id>[^/.]+)/due-date")
    def update_workflow_due_date(self, request, pk=None, workflow_id=None):
        """Update the due date for the current workflow step and sync application due date."""
        from api.serializers.doc_workflow_serializer import DocWorkflowSerializer

        workflow = self._get_application_workflow_or_none(application_id=pk, workflow_id=workflow_id)
        if not workflow:
            return self.error_response("Workflow not found", status.HTTP_404_NOT_FOUND)

        deprecated_response = self._ensure_application_product_is_active(workflow.doc_application)
        if deprecated_response:
            return deprecated_response

        due_date = self._parse_request_date(request.data.get("due_date"))
        if due_date is None:
            return self.error_response("Invalid workflow due date", status.HTTP_400_BAD_REQUEST)
        if workflow.start_date and due_date < workflow.start_date:
            return self.error_response("Workflow due date cannot be before start date", status.HTTP_400_BAD_REQUEST)

        application = workflow.doc_application
        current_workflow = application.current_workflow
        if not current_workflow or current_workflow.id != workflow.id:
            return self.error_response("Only the current task due date can be updated", status.HTTP_400_BAD_REQUEST)

        previous_due_date = application.due_date
        with transaction.atomic():
            workflow.due_date = due_date
            workflow.updated_by = request.user
            workflow.save()

            application.due_date = due_date
            application.updated_by = request.user
            application.save()
            self._queue_calendar_sync(
                application_id=application.id,
                user_id=request.user.id,
                previous_due_date=previous_due_date,
            )

        return Response(DocWorkflowSerializer(workflow).data, status=status.HTTP_200_OK)

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses=DocApplicationDetailSerializer,
        parameters=[OpenApiParameter("workflow_id", OpenApiTypes.INT, OpenApiParameter.PATH)],
    )
    @action(detail=True, methods=["post"], url_path=r"workflows/(?P<workflow_id>[^/.]+)/rollback")
    def rollback_workflow(self, request, pk=None, workflow_id=None):
        """Remove the current workflow step and reopen the previous step."""
        from customer_applications.models.doc_workflow import DocWorkflow

        workflow = self._get_application_workflow_or_none(application_id=pk, workflow_id=workflow_id)
        if not workflow:
            return self.error_response("Workflow not found", status.HTTP_404_NOT_FOUND)

        deprecated_response = self._ensure_application_product_is_active(workflow.doc_application)
        if deprecated_response:
            return deprecated_response

        application = workflow.doc_application
        current_workflow = application.current_workflow
        if not current_workflow or current_workflow.id != workflow.id:
            return self.error_response("Only the current task can be rolled back", status.HTTP_400_BAD_REQUEST)
        if workflow.task.step <= 1:
            return self.error_response("Step 1 cannot be rolled back", status.HTTP_400_BAD_REQUEST)

        previous_workflow = self._get_previous_workflow(workflow)
        if not previous_workflow:
            return self.error_response("Previous workflow not found", status.HTTP_400_BAD_REQUEST)

        previous_due_date = application.due_date
        with transaction.atomic():
            workflow.delete()

            previous_workflow.status = DocApplication.STATUS_PENDING
            previous_workflow.updated_by = request.user
            previous_workflow.save()

            application.refresh_from_db()
            current_after_rollback = application.current_workflow
            if current_after_rollback and current_after_rollback.due_date:
                application.due_date = current_after_rollback.due_date
            application.updated_by = request.user
            application.save()

            self._queue_calendar_sync(
                application_id=application.id,
                user_id=request.user.id,
                previous_due_date=previous_due_date,
            )

        application.refresh_from_db()
        return Response(self._serialize_application_detail(application), status=status.HTTP_200_OK)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="reopen")
    def reopen_application(self, request, pk=None):
        """Re-open a completed application."""
        application = self.get_object()
        deprecated_response = self._ensure_application_product_is_active(application)
        if deprecated_response:
            return deprecated_response
        if not application.reopen(request.user):
            return self.error_response("Application is not completed", status.HTTP_400_BAD_REQUEST)
        return Response(build_success_payload({"success": True}, request=request))

    @extend_schema(request=None, responses=DocApplicationDetailSerializer)
    @action(detail=True, methods=["post"], url_path="force-close")
    def force_close(self, request, pk=None):
        """Force close an application by setting its status to completed.

        This mirrors the legacy Django view behavior and bypasses automatic
        status recalculation by saving with skip_status_calculation=True.
        """
        try:
            application = self.get_object()
        except DocApplication.DoesNotExist:
            return self.error_response("Application not found", status.HTTP_404_NOT_FOUND)

        deprecated_response = self._ensure_application_product_is_active(application)
        if deprecated_response:
            return deprecated_response

        # Permission check
        if not request.user.has_perm("customer_applications.change_docapplication"):
            return self.error_response("Permission denied", status.HTTP_403_FORBIDDEN)

        if application.status == DocApplication.STATUS_COMPLETED:
            return self.error_response("Application already completed", status.HTTP_400_BAD_REQUEST)
        if application.status == DocApplication.STATUS_REJECTED:
            return self.error_response("Rejected applications cannot be force closed", status.HTTP_400_BAD_REQUEST)

        application.status = DocApplication.STATUS_COMPLETED
        application.updated_by = request.user
        application.save(skip_status_calculation=True)

        # Return serialized application detail
        serializer = DocApplicationDetailSerializer(
            application,
            context={
                "request": request,
                "prefer_cached_file_url": True,
            },
        )
        return Response(serializer.data)


class DocumentViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "patch", "put", "post"]

    def get_queryset(self):
        return Document.objects.select_related("doc_application", "doc_type", "updated_by", "created_by")

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        """Override to trigger AI validation when requested."""
        response = super().partial_update(request, *args, **kwargs)

        ai_status_override_raw = request.data.get("ai_validation_status_override", None)
        ai_result_override_raw = request.data.get("ai_validation_result_override", None)
        ai_status_override = None if ai_status_override_raw is None else str(ai_status_override_raw)
        ai_result_override = ai_result_override_raw
        if isinstance(ai_result_override_raw, str):
            text = ai_result_override_raw.strip()
            if not text:
                ai_result_override = None
            else:
                try:
                    ai_result_override = json.loads(text)
                except json.JSONDecodeError:
                    ai_result_override = None

        if response.status_code == 200 and ai_status_override is not None:
            document = self.get_object()
            allowed_overrides = {
                Document.AI_VALIDATION_NONE,
                Document.AI_VALIDATION_VALID,
                Document.AI_VALIDATION_INVALID,
                Document.AI_VALIDATION_ERROR,
            }
            if ai_status_override in allowed_overrides:
                document.ai_validation_status = ai_status_override
                # Keep AI "reason" payload only for explicitly invalid outcomes.
                document.ai_validation_result = (
                    ai_result_override if ai_status_override == Document.AI_VALIDATION_INVALID else None
                )
                document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])
                response.data = self.get_serializer(document).data
                return response

        validate_with_ai_value = request.data.get("validate_with_ai", "")
        if isinstance(validate_with_ai_value, bool):
            validate_with_ai = validate_with_ai_value
        else:
            validate_with_ai = str(validate_with_ai_value).lower() in ("true", "1", "yes")

        if validate_with_ai and response.status_code == 200:
            document = self.get_object()
            if document.doc_type and document.doc_type.ai_validation and document.file and document.file.name:
                document.ai_validation_status = Document.AI_VALIDATION_PENDING
                document.ai_validation_result = None
                document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])
                run_document_validation(document.id)
                # Re-serialize to include pending validation status
                response.data = self.get_serializer(document).data
            elif document.doc_type and not document.doc_type.ai_validation:
                document.ai_validation_status = Document.AI_VALIDATION_NONE
                document.ai_validation_result = None
                document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])
                response.data = self.get_serializer(document).data

        return response

    @extend_schema(parameters=[OpenApiParameter("action_name", OpenApiTypes.STR, OpenApiParameter.PATH)])
    @action(detail=True, methods=["post"], url_path=r"actions/(?P<action_name>[^/.]+)")
    def execute_action(self, request, pk=None, action_name=None):
        """Execute a document type hook action.

        Args:
            pk: The document ID.
            action_name: The name of the action to execute.

        Returns:
            JSON response with success status and message or error.
        """
        from customer_applications.hooks.registry import hook_registry

        document = self.get_object()

        if not document.doc_type:
            return self.error_response("Document has no type", status.HTTP_400_BAD_REQUEST)

        hook = hook_registry.get_hook(document.doc_type.name)
        if not hook:
            return self.error_response(
                "No hook registered for this document type",
                status.HTTP_400_BAD_REQUEST,
            )

        # Verify the action exists for this hook
        available_actions = [action.name for action in hook.get_extra_actions()]
        if action_name not in available_actions:
            return self.error_response(
                f"Unknown action: {action_name}",
                status.HTTP_400_BAD_REQUEST,
            )

        result = hook.execute_action(action_name, document, request)

        if result.get("success"):
            # Return updated document data
            document.refresh_from_db()
            serializer = self.get_serializer(document)
            return Response(
                {
                    "success": True,
                    "message": result.get("message", "Action completed successfully"),
                    "document": serializer.data,
                }
            )
        else:
            return self.error_response(
                result.get("error", "Action failed"),
                status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["get"], url_path="download")
    def download_file(self, request, pk=None):
        """Download the document file with authentication."""
        document = self.get_object()
        if not document.file:
            return self.error_response("Document has no file", status.HTTP_404_NOT_FOUND)

        try:
            file_handle = default_storage.open(document.file.name, "rb")
        except Exception:
            return self.error_response("File not found", status.HTTP_404_NOT_FOUND)

        content_type, _ = mimetypes.guess_type(document.file.name)
        response = FileResponse(file_handle, content_type=content_type or "application/octet-stream")
        response["Content-Disposition"] = f'inline; filename="{os.path.basename(document.file.name)}"'
        return response

    @action(detail=True, methods=["get"], url_path="print")
    def get_print_data(self, request, pk=None):
        """Get document data for print view.

        Returns the document with nested doc_application data including customer info.
        """
        from api.serializers.customer_serializer import CustomerSerializer
        from api.serializers.product_serializer import ProductSerializer

        document = self.get_object()
        doc_application = document.doc_application

        data = {
            "id": document.id,
            "docType": {
                "name": document.doc_type.name if document.doc_type else "",
                "aiValidation": document.doc_type.ai_validation if document.doc_type else False,
            },
            "docApplication": {
                "id": doc_application.id if doc_application else None,
                "customer": (
                    CustomerSerializer(doc_application.customer).data
                    if doc_application and doc_application.customer
                    else None
                ),
                "product": (
                    ProductSerializer(doc_application.product).data
                    if doc_application and doc_application.product
                    else None
                ),
            },
            "docNumber": document.doc_number,
            "expirationDate": str(document.expiration_date) if document.expiration_date else None,
            "details": document.details,
            "fileLink": document.file_link,
            "thumbnailLink": document.thumbnail_link,
            "aiValidation": document.ai_validation,
            "completed": document.completed,
        }
        return Response(data)

    @extend_schema(request=DocumentMergeSerializer, responses={200: OpenApiTypes.BINARY})
    @action(detail=False, methods=["post"], url_path="merge-pdf")
    def merge_pdf(self, request):
        """Merge selected documents into a single PDF.

        Expects JSON: {"document_ids": [1, 2, 3]}
        """
        serializer = DocumentMergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document_ids = serializer.validated_data.get("document_ids", [])

        # Get documents and preserve order
        documents_dict = {
            doc.pk: doc
            for doc in Document.objects.filter(
                pk__in=document_ids,
                completed=True,
            ).select_related("doc_type", "doc_application__customer")
        }

        if not documents_dict:
            return self.error_response("No valid documents found.", status.HTTP_404_NOT_FOUND)

        ordered_documents = [documents_dict[doc_id] for doc_id in document_ids if doc_id in documents_dict]
        documents_with_files = [doc for doc in ordered_documents if doc.file and doc.file.name]

        if not documents_with_files:
            return self.error_response("Selected documents have no uploaded files.", status.HTTP_400_BAD_REQUEST)

        # Get filename info from first doc
        application = documents_with_files[0].doc_application
        customer_name = application.customer.full_name if application and application.customer else "documents"

        try:
            merged_pdf = DocumentMerger.merge_document_models(ordered_documents)

            safe_customer_name = slugify(customer_name, allow_unicode=False).replace("-", "_")
            filename = f"documents_{safe_customer_name}_{application.pk if application else 'merged'}.pdf"
            filename = filename[:200]

            from django.http import HttpResponse

            response = HttpResponse(merged_pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            response["Content-Length"] = len(merged_pdf)

            return response

        except DocumentMergerError as e:
            return self.error_response(f"Failed to merge documents: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception("Unexpected error merging documents")
            return self.error_response("An unexpected error occurred", status.HTTP_500_INTERNAL_SERVER_ERROR)


class OCRViewSet(ApiErrorHandlingMixin, viewsets.ViewSet):
    serializer_class = OCRPlaceholderSerializer
    """
    API endpoint for passport OCR extraction.

    Supports hybrid extraction mode with AI vision for enhanced data extraction.

    POST Parameters:
        - file: The passport image or PDF file
        - doc_type: Document type (e.g., 'passport')
        - use_ai: (optional) Set to 'true' to enable AI-enhanced extraction (default: false)
        - save_session: (optional) Save file and data to session
        - img_preview: (optional) Return base64 preview image
        - resize: (optional) Resize the image
        - width: (optional) Target width for resize

    Returns:
        - mrz_data: Extracted passport data (enhanced with AI data if use_ai=true)
        - preview_url: Signed preview URL when available (if img_preview=true)
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "ocr"
    throttle_classes = [ScopedRateThrottle]

    def get_throttles(self):
        if getattr(self, "action", None) in {"status", "stream"}:
            self.throttle_scope = "ocr_status"
        else:
            self.throttle_scope = "ocr"
        return super().get_throttles()

    @action(detail=False, methods=["post"], url_path="check")
    def check(self, request):
        from django.utils.text import get_valid_filename

        namespace = "passport_ocr_check"
        file = request.data.get("file")
        if not file or file == "undefined":
            return self.error_response("No file provided!", status.HTTP_400_BAD_REQUEST)

        valid_file_types = ["image/jpeg", "image/png", "image/tiff", "application/pdf"]
        file_type = mimetypes.guess_type(file.name)[0]
        if file_type not in valid_file_types:
            return self.error_response(
                "File format not supported. Only images (jpeg and png) and pdf are accepted!",
                status.HTTP_400_BAD_REQUEST,
            )

        doc_type_raw = request.data.get("doc_type")
        if not doc_type_raw or doc_type_raw == "undefined":
            return self.error_response("No doc_type provided!", status.HTTP_400_BAD_REQUEST)
        doc_type = doc_type_raw.lower()

        # Check if AI extraction is requested
        use_ai = str(request.data.get("use_ai", "false")).lower() == "true"
        save_session = str(request.data.get("save_session", "false")).lower() == "true"
        img_preview = str(request.data.get("img_preview", "false")).lower() == "true"
        resize = str(request.data.get("resize", "false")).lower() == "true"
        width = request.data.get("width", None)

        idempotency_cache_key, cached_job = resolve_request_idempotent_job(
            request=request,
            namespace=namespace,
            user_id=request.user.id,
            queryset=OCRJob.objects.filter(created_by=request.user),
        )
        if cached_job is not None:
            return Response(
                build_async_job_start_payload(
                    job_id=cached_job.id,
                    status=cached_job.status,
                    progress=cached_job.progress,
                    queued=False,
                    deduplicated=True,
                    links=build_async_job_links(
                        request,
                        cached_job.id,
                        status_route="api-ocr-status",
                        stream_route="api-ocr-stream",
                    ),
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        def build_existing_response(existing_job):
            return Response(
                build_async_job_start_payload(
                    job_id=existing_job.id,
                    status=existing_job.status,
                    progress=existing_job.progress,
                    queued=False,
                    deduplicated=True,
                    links=build_async_job_links(
                        request,
                        existing_job.id,
                        status_route="api-ocr-status",
                        stream_route="api-ocr-stream",
                    ),
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        guard = prepare_async_enqueue(
            namespace=namespace,
            user=request.user,
            inflight_queryset=OCRJob.objects.filter(created_by=request.user),
            inflight_statuses=QUEUE_JOB_INFLIGHT_STATUSES,
            busy_message="OCR trigger is already being processed. Please retry in a moment.",
            deduplicated_response_builder=build_existing_response,
            error_response_builder=self.error_response,
        )
        if guard.response is not None:
            return guard.response

        lock_key = guard.lock_key
        lock_token = guard.lock_token
        try:
            safe_filename = get_valid_filename(os.path.basename(file.name))
            tmp_file_path = os.path.join(getattr(settings, "TMPFILES_FOLDER", "tmpfiles"), safe_filename)
            file_path = default_storage.save(tmp_file_path, file)

            job = OCRJob.objects.create(
                status=OCRJob.STATUS_QUEUED,
                progress=0,
                file_path=file_path,
                file_url=default_storage.url(file_path),
                created_by=request.user,
                save_session=save_session,
                request_params={
                    "doc_type": doc_type,
                    "use_ai": use_ai,
                    "img_preview": img_preview,
                    "resize": resize,
                    "width": width,
                },
            )
            run_ocr_job(str(job.id))
            store_request_idempotent_job(cache_key=idempotency_cache_key, job_id=job.id)

            return Response(
                build_async_job_start_payload(
                    job_id=job.id,
                    status=OCRJob.STATUS_QUEUED,
                    progress=job.progress,
                    queued=True,
                    deduplicated=False,
                    links=build_async_job_links(
                        request,
                        job.id,
                        status_route="api-ocr-status",
                        stream_route="api-ocr-stream",
                    ),
                ),
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception as e:
            errMsg = e.args[0] if e.args else str(e)
            return self.error_response(errMsg, status.HTTP_400_BAD_REQUEST)
        finally:
            if lock_key and lock_token:
                release_enqueue_guard(lock_key, lock_token)

    @action(detail=False, methods=["get"], url_path=r"status/(?P<job_id>[^/.]+)")
    def status(self, request, job_id=None):
        job = restrict_to_owner_unless_privileged(OCRJob.objects.filter(id=job_id), request.user).first()
        if not job:
            return self.error_response("OCR job not found", status.HTTP_404_NOT_FOUND)

        return Response(data=_build_ocr_status_payload(job, request), status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path=r"stream/(?P<job_id>[^/.]+)")
    def stream(self, request, job_id=None):
        job_queryset = restrict_to_owner_unless_privileged(OCRJob.objects.filter(id=job_id), request.user)
        job = job_queryset.first()
        if not job:
            return self.error_response("OCR job not found", status.HTTP_404_NOT_FOUND)

        response = StreamingHttpResponse(
            self._stream_ocr_job(request, job_queryset, job, last_event_id=resolve_last_event_id(request)),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _stream_ocr_job(self, request, job_queryset, job: OCRJob, *, last_event_id: str | None = None):

        def _sync_stream():
            stream_key = stream_job_key(job.id)
            deadline = time.monotonic() + 55
            initial_payload = _build_ocr_status_payload(job, request)
            last_progress = initial_payload["progress"]
            last_status = initial_payload["status"]

            logger.info("ocr_stream_connect job_id=%s replay_cursor=%s", job.id, last_event_id)
            yield format_sse_event(data=initial_payload)
            if last_status in {OCRJob.STATUS_COMPLETED, OCRJob.STATUS_FAILED}:
                return

            for stream_event in iter_replay_and_live_events(
                stream_key=stream_key, last_event_id=last_event_id
            ):
                if time.monotonic() >= deadline:
                    return
                try:
                    if stream_event is None:
                        yield ": keepalive\n\n"
                        continue

                    data = normalize_ocr_job_payload(stream_event.payload)
                    if data is None or data["status"] in {OCRJob.STATUS_COMPLETED, OCRJob.STATUS_FAILED}:
                        refreshed_job = job_queryset.get()
                        data = _build_ocr_status_payload(refreshed_job, request)
                    else:
                        data = _build_ocr_stream_payload(data)

                    if data["progress"] == last_progress and data["status"] == last_status:
                        continue

                    yield format_sse_event(event_id=stream_event.id, data=data)
                    last_progress = data["progress"]
                    last_status = data["status"]

                    if last_status in {OCRJob.STATUS_COMPLETED, OCRJob.STATUS_FAILED}:
                        return
                except OCRJob.DoesNotExist:
                    logger.warning("ocr_stream_job_not_found job_id=%s replay_cursor=%s", job.id, last_event_id)
                    yield format_sse_event(data={"errorMessage": "OCR job not found"})
                    return
                except Exception as exc:
                    logger.exception("ocr_stream_failure job_id=%s error=%s", job.id, exc)
                    yield format_sse_event(data={"errorMessage": str(exc)})
                    return

        return _sync_stream()


class DocumentOCRViewSet(ApiErrorHandlingMixin, viewsets.ViewSet):
    serializer_class = DocumentOCRPlaceholderSerializer
    """
    API endpoint for document OCR text extraction.

    POST Parameters:
        - file: The document file (PDF, Excel, Word)

    Returns:
        - text: Extracted text when completed
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "document_ocr"
    throttle_classes = [ScopedRateThrottle]

    def get_throttles(self):
        if getattr(self, "action", None) in {"status", "stream"}:
            self.throttle_scope = "document_ocr_status"
        else:
            self.throttle_scope = "document_ocr"
        return super().get_throttles()

    @action(detail=False, methods=["post"], url_path="check")
    def check(self, request):
        from django.utils.text import get_valid_filename

        namespace = "document_ocr_check"
        file = request.data.get("file")
        if not file or file == "undefined":
            return self.error_response("No file provided!", status.HTTP_400_BAD_REQUEST)

        valid_file_types = {
            ".pdf": "application/pdf",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".bmp": "image/bmp",
        }

        file_type = mimetypes.guess_type(file.name)[0]
        file_ext = os.path.splitext(file.name)[1].lower()
        if not file_type:
            file_type = valid_file_types.get(file_ext)

        if file_ext not in valid_file_types or file_type not in valid_file_types.values():
            return self.error_response(
                "File format not supported. Only PDF, Excel, Word, and image files are accepted!",
                status.HTTP_400_BAD_REQUEST,
            )

        resolved_doc_type_id: int | None = None
        resolved_document_id: int | None = None
        document_id_raw = request.data.get("document_id")
        doc_type_id_raw = request.data.get("doc_type_id")

        if document_id_raw not in (None, ""):
            try:
                document_id = int(document_id_raw)
            except (TypeError, ValueError):
                return self.error_response("Invalid document_id", status.HTTP_400_BAD_REQUEST)

            document = restrict_to_owner_unless_privileged(
                Document.objects.select_related("doc_type").filter(id=document_id),
                request.user,
            ).first()
            if not document:
                return self.error_response("Document not found", status.HTTP_404_NOT_FOUND)

            if document.doc_type_id:
                resolved_doc_type_id = int(document.doc_type_id)
            resolved_document_id = int(document.id)
        elif doc_type_id_raw not in (None, ""):
            try:
                resolved_doc_type_id = int(doc_type_id_raw)
            except (TypeError, ValueError):
                return self.error_response("Invalid doc_type_id", status.HTTP_400_BAD_REQUEST)

        idempotency_cache_key, cached_job = resolve_request_idempotent_job(
            request=request,
            namespace=namespace,
            user_id=request.user.id,
            queryset=DocumentOCRJob.objects.filter(created_by=request.user),
        )
        if cached_job is not None:
            return Response(
                build_async_job_start_payload(
                    job_id=cached_job.id,
                    status=cached_job.status,
                    progress=cached_job.progress,
                    queued=False,
                    deduplicated=True,
                    links=build_async_job_links(
                        request,
                        cached_job.id,
                        status_route="api-document-ocr-status",
                        stream_route="api-document-ocr-stream",
                    ),
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        def build_existing_response(existing_job):
            return Response(
                build_async_job_start_payload(
                    job_id=existing_job.id,
                    status=existing_job.status,
                    progress=existing_job.progress,
                    queued=False,
                    deduplicated=True,
                    links=build_async_job_links(
                        request,
                        existing_job.id,
                        status_route="api-document-ocr-status",
                        stream_route="api-document-ocr-stream",
                    ),
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        guard = prepare_async_enqueue(
            namespace=namespace,
            user=request.user,
            inflight_queryset=DocumentOCRJob.objects.filter(created_by=request.user),
            inflight_statuses=QUEUE_JOB_INFLIGHT_STATUSES,
            busy_message="Document OCR trigger is already being processed. Please retry in a moment.",
            deduplicated_response_builder=build_existing_response,
            error_response_builder=self.error_response,
        )
        if guard.response is not None:
            return guard.response

        lock_key = guard.lock_key
        lock_token = guard.lock_token
        try:
            safe_filename = get_valid_filename(os.path.basename(file.name))
            job_uuid = uuid.uuid4()
            tmp_file_path = os.path.join(
                getattr(settings, "TMPFILES_FOLDER", "tmpfiles"), "document_ocr", str(job_uuid), safe_filename
            )
            file_path = default_storage.save(tmp_file_path, file)

            job = DocumentOCRJob.objects.create(
                id=job_uuid,
                status=DocumentOCRJob.STATUS_QUEUED,
                progress=0,
                file_path=file_path,
                file_url=default_storage.url(file_path),
                created_by=request.user,
                request_params={
                    "file_type": file_type,
                    "doc_type_id": resolved_doc_type_id,
                    "document_id": resolved_document_id,
                },
            )
            run_document_ocr_job(str(job.id))
            store_request_idempotent_job(cache_key=idempotency_cache_key, job_id=job.id)
            return Response(
                build_async_job_start_payload(
                    job_id=job.id,
                    status=DocumentOCRJob.STATUS_QUEUED,
                    progress=job.progress,
                    queued=True,
                    deduplicated=False,
                    links=build_async_job_links(
                        request,
                        job.id,
                        status_route="api-document-ocr-status",
                        stream_route="api-document-ocr-stream",
                    ),
                ),
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception as e:
            errMsg = e.args[0] if e.args else str(e)
            return self.error_response(errMsg, status.HTTP_400_BAD_REQUEST)
        finally:
            if lock_key and lock_token:
                release_enqueue_guard(lock_key, lock_token)

    @action(detail=False, methods=["get"], url_path=r"status/(?P<job_id>[^/.]+)")
    def status(self, request, job_id=None):
        job = restrict_to_owner_unless_privileged(DocumentOCRJob.objects.filter(id=job_id), request.user).first()
        if not job:
            return self.error_response("Document OCR job not found", status.HTTP_404_NOT_FOUND)

        return Response(data=_build_document_ocr_status_payload(job), status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path=r"stream/(?P<job_id>[^/.]+)")
    def stream(self, request, job_id=None):
        job_queryset = restrict_to_owner_unless_privileged(DocumentOCRJob.objects.filter(id=job_id), request.user)
        job = job_queryset.first()
        if not job:
            return self.error_response("Document OCR job not found", status.HTTP_404_NOT_FOUND)

        response = StreamingHttpResponse(
            self._stream_document_ocr_job(job_queryset, job, last_event_id=resolve_last_event_id(request)),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _stream_document_ocr_job(self, job_queryset, job: DocumentOCRJob, *, last_event_id: str | None = None):

        def _sync_stream():
            stream_key = stream_job_key(job.id)
            deadline = time.monotonic() + 55
            initial_payload = _build_document_ocr_status_payload(job)
            last_progress = initial_payload["progress"]
            last_status = initial_payload["status"]

            logger.info("document_ocr_stream_connect job_id=%s replay_cursor=%s", job.id, last_event_id)
            yield format_sse_event(data=initial_payload)
            if last_status in {DocumentOCRJob.STATUS_COMPLETED, DocumentOCRJob.STATUS_FAILED}:
                return

            for stream_event in iter_replay_and_live_events(
                stream_key=stream_key, last_event_id=last_event_id
            ):
                if time.monotonic() >= deadline:
                    return
                try:
                    if stream_event is None:
                        yield ": keepalive\n\n"
                        continue

                    data = normalize_document_ocr_job_payload(stream_event.payload)
                    if data is None or data["status"] in {
                        DocumentOCRJob.STATUS_COMPLETED,
                        DocumentOCRJob.STATUS_FAILED,
                    }:
                        refreshed_job = job_queryset.get()
                        data = _build_document_ocr_status_payload(refreshed_job)
                    else:
                        data = _build_document_ocr_stream_payload(data)

                    if data["progress"] == last_progress and data["status"] == last_status:
                        continue

                    yield format_sse_event(event_id=stream_event.id, data=data)
                    last_progress = data["progress"]
                    last_status = data["status"]

                    if last_status in {DocumentOCRJob.STATUS_COMPLETED, DocumentOCRJob.STATUS_FAILED}:
                        return
                except DocumentOCRJob.DoesNotExist:
                    logger.warning(
                        "document_ocr_stream_job_not_found job_id=%s replay_cursor=%s",
                        job.id,
                        last_event_id,
                    )
                    yield format_sse_event(data={"errorMessage": "Document OCR job not found"})
                    return
                except Exception as exc:
                    logger.exception("document_ocr_stream_failure job_id=%s error=%s", job.id, exc)
                    yield format_sse_event(data={"errorMessage": str(exc)})
                    return

        return _sync_stream()


# the urlpattern for this view is:
"""
    path(
        "compute/doc_workflow_due_date/int:<task_id>/date:start_date>/",
        views.ComputeDocworkflowDueDate.as_view(),
        name="api-compute-docworkflow-due-date",
    ),

"""


class ComputeViewSet(ApiErrorHandlingMixin, viewsets.ViewSet):
    serializer_class = ComputePlaceholderSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="doc_workflow_due_date/(?P<task_id>[^/.]+)/(?P<start_date>[^/.]+)")
    def doc_workflow_due_date(self, request, task_id=None, start_date=None):
        task_id = self.kwargs.get("task_id")
        start_date = self.kwargs.get("start_date")
        # check that the date is a valid date and convert it to a datetime object
        if start_date:
            try:
                start_date = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                return self.error_response("Invalid date format. Date must be in the format YYYY-MM-DD")
        if task_id:
            try:
                task = Task.objects.get(id=task_id)
                due_date = calculate_due_date(start_date, task.duration, task.duration_is_business_days)
                due_date = due_date.strftime("%Y-%m-%d")
                return Response({"dueDate": due_date})
            except Task.DoesNotExist:
                return self.error_response("Task does not exist", status.HTTP_404_NOT_FOUND)
        else:
            return self.error_response("Invalid request", status.HTTP_400_BAD_REQUEST)


class DashboardStatsView(ApiErrorHandlingMixin, viewsets.ViewSet):
    serializer_class = DashboardStatsSerializer
    """
    API endpoint for dashboard statistics.
    TO BE REMOVED WHEN ANGULAR FRONTEND IS COMPLETE
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: DashboardStatsSerializer})
    def list(self, request):
        stats = {
            "customers": Customer.objects.count(),
            "applications": DocApplication.objects.filter(
                status__in=[DocApplication.STATUS_PENDING, DocApplication.STATUS_PROCESSING]
            ).count(),
            "invoices": InvoiceApplication.objects.not_fully_paid().count(),
        }
        return Response(stats)


@api_view(["GET", "POST"])
@authentication_classes([JwtOrMockAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsStaffOrAdminGroup])
@throttle_classes([CronScopedRateThrottle])
def exec_cron_jobs(request):
    """
    Execute cron jobs via Dramatiq.
    """
    full_backup_queued = enqueue_full_backup_now()
    clear_cache_queued = enqueue_clear_cache_now()
    if full_backup_queued and clear_cache_queued:
        status_label = "queued"
    elif full_backup_queued or clear_cache_queued:
        status_label = "partially_queued"
    else:
        status_label = "already_queued"
    return Response(
        {
            "status": status_label,
            "fullBackupQueued": full_backup_queued,
            "clearCacheQueued": clear_cache_queued,
        },
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def mock_auth_config(request):
    from core.services.app_setting_service import AppSettingService

    if not AppSettingService.parse_bool(AppSettingService.get_effective_raw("MOCK_AUTH_ENABLED", False), False):
        return Response(
            build_error_payload(
                code="mock_auth_disabled",
                message="Mock authentication is disabled.",
                details={"detail": ["Mock authentication is disabled."]},
                request=request,
            ),
            status=status.HTTP_403_FORBIDDEN,
        )

    username = getattr(settings, "MOCK_AUTH_USERNAME", "mockuser")
    email = getattr(settings, "MOCK_AUTH_EMAIL", "mock@example.com")

    return Response(
        build_success_payload(
            {
                "sub": username,
                "username": username,
                "email": email,
                "is_superuser": getattr(settings, "MOCK_AUTH_IS_SUPERUSER", True),
                "is_staff": getattr(settings, "MOCK_AUTH_IS_STAFF", True),
                "groups": getattr(settings, "MOCK_AUTH_GROUPS", []),
                "roles": getattr(settings, "MOCK_AUTH_ROLES", []),
            },
            request=request,
        )
    )


@api_view(["POST"])
@csrf_exempt
@authentication_classes([JwtOrMockAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([QuickCreateScopedRateThrottle])
def customer_quick_create(request):
    """
    Quick create a customer with minimal required fields
    """
    try:
        serializer = CustomerQuickCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                build_error_payload(
                    code="validation_error",
                    message="Validation error",
                    details=serializer.errors,
                    request=request,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer = create_quick_customer(validated_data=serializer.validated_data)

        return Response(
            build_success_payload(
                {
                    "success": True,
                    "customer": {
                        "id": customer.id,
                        "full_name": customer.full_name_with_company,
                        "email": customer.email or "",
                        "telephone": customer.telephone or "",
                        "company_name": customer.company_name or "",
                        "npwp": customer.npwp or "",
                        "passport_number": customer.passport_number or "",
                        "passport_expiration_date": (
                            str(customer.passport_expiration_date) if customer.passport_expiration_date else ""
                        ),
                        "birth_place": customer.birth_place or "",
                        "address_abroad": customer.address_abroad or "",
                    },
                },
                request=request,
            ),
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        # Handle validation errors
        if hasattr(e, "message_dict"):
            # Django ValidationError
            return Response(
                build_error_payload(
                    code="validation_error",
                    message="Validation error",
                    details=getattr(e, "message_dict"),
                    request=request,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.exception("Error in customer_quick_create")
        return Response(
            build_error_payload(
                code="error",
                message="Server error while creating customer.",
                request=request,
            ),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@csrf_exempt
@authentication_classes([JwtOrMockAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([QuickCreateScopedRateThrottle])
def customer_application_quick_create(request):
    """
    Quick create a customer application with documents and workflows
    """
    try:
        serializer = CustomerApplicationQuickCreateSerializer(data=request.data)
        if not serializer.is_valid():
            if "doc_date" in serializer.errors:
                return Response(
                    build_error_payload(
                        code="validation_error",
                        message="Invalid date format. Use YYYY-MM-DD or DD/MM/YYYY.",
                        request=request,
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if "customer" in serializer.errors or "product" in serializer.errors:
                return Response(
                    build_error_payload(
                        code="not_found",
                        message="Customer or product not found.",
                        request=request,
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(
                build_error_payload(
                    code="validation_error",
                    message="Validation error",
                    details=serializer.errors,
                    request=request,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        validated_data = serializer.validated_data
        doc_app = create_quick_customer_application(
            customer=validated_data.get("customer"),
            product=validated_data.get("product"),
            doc_date=validated_data.get("doc_date"),
            notes=validated_data.get("notes", ""),
            created_by=request.user,
        )

        return Response(
            build_success_payload(
                {
                    "success": True,
                    "application": {
                        "id": doc_app.id,
                        "product_name": str(doc_app.product.name),
                        "product_code": str(doc_app.product.code),
                        "customer_name": str(doc_app.customer.full_name),
                        "doc_date": str(doc_app.doc_date),
                        "base_price": float(doc_app.product.base_price or 0),
                        "retail_price": float(doc_app.product.retail_price or doc_app.product.base_price or 0),
                        "display_name": f"{doc_app.product.code} - {doc_app.product.name} ({doc_app.customer.full_name})",
                    },
                },
                request=request,
            ),
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        # Handle validation errors
        logger.exception("Error in customer_application_quick_create")

        if hasattr(e, "message_dict"):
            # Django ValidationError
            return Response(
                build_error_payload(
                    code="validation_error",
                    message="Validation error",
                    details=getattr(e, "message_dict"),
                    request=request,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            build_error_payload(
                code="error",
                message="Server error while creating customer application.",
                request=request,
            ),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@csrf_exempt
@authentication_classes([JwtOrMockAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsAdminOrManagerGroup])
@throttle_classes([QuickCreateScopedRateThrottle])
def product_quick_create(request):
    """
    Quick create a product with minimal required fields
    """
    try:
        serializer = ProductQuickCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                build_error_payload(
                    code="validation_error",
                    message="Validation error",
                    details=serializer.errors,
                    request=request,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = create_quick_product(validated_data=serializer.validated_data, user=request.user)

        return Response(
            build_success_payload(
                {
                    "success": True,
                    "product": {
                        "id": product.id,
                        "name": product.name,
                        "code": product.code,
                        "product_type": product.product_category.product_type if product.product_category else None,
                        "base_price": product.base_price,
                        "retail_price": product.retail_price,
                        "created_at": product.created_at,
                        "updated_at": product.updated_at,
                        "created_by": product.created_by_id,
                        "updated_by": product.updated_by_id,
                    },
                },
                request=request,
            ),
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        # Handle validation errors
        if hasattr(e, "message_dict"):
            # Django ValidationError
            return Response(
                build_error_payload(
                    code="validation_error",
                    message="Validation error",
                    details=getattr(e, "message_dict"),
                    request=request,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.exception("Error in product_quick_create")
        return Response(
            build_error_payload(
                code="error",
                message="Server error while creating product.",
                request=request,
            ),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
