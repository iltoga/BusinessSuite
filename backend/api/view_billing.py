"""
api.view_billing
================
DRF ViewSet controllers for invoice management.

``InvoiceViewSet`` (ModelViewSet)
----------------------------------
- **list / retrieve / create / update / partial_update / destroy** — standard
  CRUD; ``create`` / ``update`` use ``InvoiceCreateUpdateSerializer``,
  ``retrieve`` uses ``InvoiceDetailSerializer``, ``list`` uses
  ``InvoiceListSerializer``.
- **search** — ``search`` and ``q`` query params forwarded to
  ``Invoice.objects.search_invoices()``.
- **hide_paid** — boolean query param to exclude ``PAID`` invoices.
- Permission: ``IsAuthenticated`` (row-level via customer ownership implied).

Async job actions
-----------------
- **download_pdf** (POST) — enqueues an ``InvoiceDownloadJob`` actor on the
  ``default`` queue; returns ``{job_id, status}``.
- **import_rows** (POST) — enqueues an ``InvoiceImportJob`` actor; returns
  ``{job_id, status}``.

SSE payload shapes
------------------
All async jobs stream updates via ``/api/async-jobs/status/{job_id}/``.  The
download job payload is serialised by
``serialize_invoice_download_job_payload()``; the import job payload by
``serialize_invoice_import_job_payload()`` / ``serialize_invoice_import_item_payload()``.

Helper functions
-----------------
- ``_download_stream_payload_from_job(job)`` — build SSE payload dict from a
  loaded ``InvoiceDownloadJob`` ORM instance.
- ``_load_download_stream_payload(job_id)`` — load by id and build payload, or
  return ``None`` if the job does not exist.
- ``_import_job_stream_payload_from_job(job)`` — same for import jobs.
- ``_import_item_stream_payload_from_item(item)`` — per-item progress payload.
"""

from api.utils.contracts import build_success_payload
from api.utils.idempotency import build_request_idempotency_fingerprint, resolve_request_idempotent_job, store_request_idempotent_job
from api.utils.stream_payloads import (
    build_async_job_links,
    build_async_job_start_payload,
    first_present,
    normalize_invoice_download_job_payload,
    normalize_invoice_import_item_payload,
    normalize_invoice_import_job_payload,
    serialize_invoice_download_job_payload,
    serialize_invoice_import_item_payload,
    serialize_invoice_import_job_payload,
)
from core.services.app_setting_service import AppSettingService

from .views_imports import *


def _download_stream_payload_from_job(job) -> dict[str, Any]:
    return serialize_invoice_download_job_payload(job)


def _load_download_stream_payload(job_id) -> dict[str, Any] | None:
    job = InvoiceDownloadJob.objects.filter(id=job_id).first()
    if not job:
        return None
    return _download_stream_payload_from_job(job)


def _import_job_stream_payload_from_job(job) -> dict[str, Any]:
    return serialize_invoice_import_job_payload(job)


def _import_item_stream_payload_from_item(item) -> dict[str, Any]:
    return serialize_invoice_import_item_payload(item)


class InvoiceViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    throttle_scope = None
    throttle_cache_fail_open_actions = {
        "download_async": False,
        "import_batch": False,
    }
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "invoice_no",
        "invoice_date",
        "due_date",
        "status",
        "customer__first_name",
        "customer__last_name",
        "customer__company_name",
    ]
    ordering_fields = ["invoice_no", "invoice_date", "due_date", "status", "total_amount", "created_at", "updated_at"]
    ordering = ["-invoice_date", "-invoice_no"]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return InvoiceCreateUpdateSerializer
        if self.action == "retrieve":
            return InvoiceDetailSerializer
        return InvoiceListSerializer

    def get_queryset(self):
        queryset = Invoice.objects.all()
        query = self.request.query_params.get("search") or self.request.query_params.get("q")
        if query:
            queryset = Invoice.objects.search_invoices(query)

        hide_paid = self.request.query_params.get("hide_paid", "false").lower() == "true"
        if hide_paid:
            queryset = queryset.exclude(status=Invoice.PAID)

        include_payment_details = self.action == "retrieve"
        return self._annotate_invoices(queryset, include_payment_details=include_payment_details)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="hide_paid",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _annotate_invoices(self, queryset, include_payment_details: bool = False):
        payment_subquery = (
            Payment.objects.filter(invoice_application__invoice=OuterRef("pk"))
            .values("invoice_application__invoice")
            .annotate(total=Sum("amount"))
            .values("total")
        )

        app_payment_subquery = (
            Payment.objects.filter(invoice_application=OuterRef("pk"))
            .values("invoice_application")
            .annotate(total=Sum("amount"))
            .values("total")
        )

        invoice_applications_qs = InvoiceApplication.objects.select_related(
            "product",
            "customer_application__product",
            "customer_application__customer",
        ).annotate(
            annotated_paid_amount=Coalesce(Subquery(app_payment_subquery), Value(0), output_field=DecimalField()),
            annotated_due_amount=F("amount")
            - Coalesce(Subquery(app_payment_subquery), Value(0), output_field=DecimalField()),
        )

        if include_payment_details:
            invoice_applications_qs = invoice_applications_qs.prefetch_related("payments")

        return (
            queryset.select_related("customer", "created_by", "updated_by")
            .prefetch_related(Prefetch("invoice_applications", queryset=invoice_applications_qs))
            .annotate(total_paid=Coalesce(Subquery(payment_subquery), Value(0), output_field=DecimalField()))
            .annotate(total_due=F("total_amount") - F("total_paid"))
        )

    def perform_create(self, serializer):
        from core.services.invoice_service import create_invoice

        invoice = create_invoice(data=serializer.validated_data, user=self.request.user)
        serializer.instance = invoice

    def perform_update(self, serializer):
        from core.services.invoice_service import update_invoice

        invoice = update_invoice(
            invoice=self.get_object(),
            data=serializer.validated_data,
            user=self.request.user,
        )
        serializer.instance = invoice

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"], url_path="delete-preview")
    def delete_preview(self, request, pk=None):
        if not is_superuser_or_admin_group(request.user):
            return self.error_response("Only superusers can delete invoices.", status.HTTP_403_FORBIDDEN)

        invoice = self.get_object()

        from invoices.services.invoice_deletion import build_invoice_delete_preview

        preview = build_invoice_delete_preview(invoice)

        return Response(
            build_success_payload(
                {
                    "invoiceNoDisplay": invoice.invoice_no_display,
                    "customerName": invoice.customer.full_name,
                    "totalAmount": invoice.total_amount,
                    "statusDisplay": invoice.get_status_display(),
                    "invoiceApplicationsCount": preview.invoice_applications_count,
                    "customerApplicationsCount": preview.customer_applications_count,
                    "paymentsCount": preview.payments_count,
                },
                request=request,
            )
        )

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="force-delete")
    def force_delete(self, request, pk=None):
        if not is_superuser_or_admin_group(request.user):
            return self.error_response("Only superusers can delete invoices.", status.HTTP_403_FORBIDDEN)

        force_confirmed = parse_bool(
            request.data.get("force_delete_confirmed")
            or request.data.get("forceDeleteConfirmed")
            or request.data.get("confirmed")
        )
        if not force_confirmed:
            return self.error_response("Please confirm the force delete action.", status.HTTP_400_BAD_REQUEST)

        delete_customer_apps = parse_bool(
            request.data.get("delete_customer_applications") or request.data.get("deleteCustomerApplications")
        )

        from invoices.services.invoice_deletion import force_delete_invoice

        invoice = self.get_object()
        result = force_delete_invoice(invoice, delete_customer_apps=delete_customer_apps)

        return Response(build_success_payload({"deleted": True, **result}, request=request))

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        if not is_superuser_or_admin_group(request.user):
            return self.error_response("Only superusers can delete invoices.", status.HTTP_403_FORBIDDEN)

        query = (
            request.data.get("search_query") or request.data.get("searchQuery") or request.data.get("query") or ""
        ).strip()
        hide_paid = parse_bool(request.data.get("hide_paid") or request.data.get("hidePaid"))
        delete_customer_apps = parse_bool(
            request.data.get("delete_customer_applications") or request.data.get("deleteCustomerApplications")
        )

        from invoices.services.invoice_deletion import bulk_delete_invoices

        result = bulk_delete_invoices(
            query=query or None,
            hide_paid=hide_paid,
            delete_customer_apps=delete_customer_apps,
        )

        return Response(build_success_payload(result, request=request))

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="file_format",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="The format of the downloaded invoice (docx or pdf).",
                enum=["docx", "pdf"],
            )
        ],
        responses={
            200: OpenApiTypes.BINARY,
        },
    )
    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        format_type = request.query_params.get("file_format", "docx").lower()

        # Validate format parameter
        if format_type not in ["docx", "pdf"]:
            return self.error_response("Invalid format. Use 'docx' or 'pdf'.", status.HTTP_400_BAD_REQUEST)

        invoice = self.get_object()
        invoice_service = InvoiceService(invoice)

        # Logic for determining invoice document content (matches legacy view)
        if invoice.total_paid_amount == 0 or invoice.is_payment_complete:
            data, items = invoice_service.generate_invoice_data()
            buf = invoice_service.generate_invoice_document(data, items)
        else:
            data, items, payments = invoice_service.generate_partial_invoice_data()
            buf = invoice_service.generate_invoice_document(data, items, payments)

        # Build filename
        raw_name = f"{invoice.invoice_no_display}_{invoice.customer.full_name}"
        safe_name = slugify(raw_name, allow_unicode=False).replace("-", "_") or f"Invoice_{pk}"
        safe_name = safe_name[:200]

        if format_type == "docx":
            return FileResponse(
                buf,
                as_attachment=True,
                filename=f"{safe_name}.docx",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        # Convert to PDF
        try:
            pdf_bytes = PDFConverter.docx_buffer_to_pdf(buf)
            pdf_buf = BytesIO(pdf_bytes)
            response = FileResponse(
                pdf_buf,
                as_attachment=True,
                filename=f"{safe_name}.pdf",
                content_type="application/pdf",
            )
            return response
        except PDFConverterError as e:
            return self.error_response(f"PDF conversion failed: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(
        detail=True,
        methods=["post"],
        url_path="download-async",
        throttle_scope="invoice_download_async",
        throttle_classes=[AnonRateThrottle, UserRateThrottle, ScopedRateThrottle],
    )
    def download_async(self, request, pk=None):
        namespace = "invoice_download_async"
        request_fingerprint = build_request_idempotency_fingerprint(request)
        format_type = (
            request.data.get("file_format")
            or request.data.get("format")
            or request.query_params.get("file_format")
            or "pdf"
        ).lower()

        if format_type not in [InvoiceDownloadJob.FORMAT_DOCX, InvoiceDownloadJob.FORMAT_PDF]:
            return self.error_response("Invalid format. Use 'docx' or 'pdf'.", status.HTTP_400_BAD_REQUEST)

        invoice = self.get_object()
        idempotency_cache_key, cached_job = resolve_request_idempotent_job(
            request=request,
            namespace=namespace,
            user_id=request.user.id,
            queryset=InvoiceDownloadJob.objects.filter(invoice=invoice, format_type=format_type, created_by=request.user),
            fingerprint=request_fingerprint,
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
                        status_route="invoices-download-async-status",
                        stream_route="invoices-download-async-stream",
                        download_route="invoices-download-async-file",
                    ),
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        stale_seconds = max(30, int(getattr(settings, "INVOICE_DOWNLOAD_STALE_SECONDS", 180) or 180))
        stale_cutoff = timezone.now() - timedelta(seconds=stale_seconds)
        stale_jobs = InvoiceDownloadJob.objects.filter(
            invoice=invoice,
            format_type=format_type,
            created_by=request.user,
            status__in=QUEUE_JOB_INFLIGHT_STATUSES,
            updated_at__lt=stale_cutoff,
        )
        stale_count = stale_jobs.count()
        if stale_count:
            stale_jobs.update(
                status=InvoiceDownloadJob.STATUS_FAILED,
                progress=100,
                output_path="",
                error_message="Stale async download job auto-failed before retry.",
                traceback="",
            )
            logger.warning(
                "Auto-failed stale invoice download jobs user_id=%s invoice_id=%s format=%s count=%s",
                getattr(request.user, "id", None),
                invoice.id,
                format_type,
                stale_count,
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
                        status_route="invoices-download-async-status",
                        stream_route="invoices-download-async-stream",
                        download_route="invoices-download-async-file",
                    ),
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        scope = f"invoice:{invoice.id}:format:{format_type}"
        guard = prepare_async_enqueue(
            namespace=namespace,
            user=request.user,
            inflight_queryset=InvoiceDownloadJob.objects.filter(
                invoice=invoice,
                format_type=format_type,
                created_by=request.user,
            ),
            inflight_statuses=QUEUE_JOB_INFLIGHT_STATUSES,
            scope=scope,
            busy_message="Invoice download trigger is already being processed. Please retry in a moment.",
            deduplicated_response_builder=build_existing_response,
            error_response_builder=self.error_response,
        )
        if guard.response is not None:
            return guard.response

        lock_key = guard.lock_key
        lock_token = guard.lock_token
        try:
            job = InvoiceDownloadJob.objects.create(
                invoice=invoice,
                status=InvoiceDownloadJob.STATUS_QUEUED,
                progress=0,
                format_type=format_type,
                created_by=request.user,
                request_params={"format": format_type},
            )

            run_invoice_download_job(str(job.id))
            store_request_idempotent_job(
                cache_key=idempotency_cache_key,
                job_id=job.id,
                fingerprint=request_fingerprint,
            )
        finally:
            if lock_key and lock_token:
                release_enqueue_guard(lock_key, lock_token)

        return Response(
            build_async_job_start_payload(
                job_id=job.id,
                status=InvoiceDownloadJob.STATUS_QUEUED,
                progress=job.progress,
                queued=True,
                deduplicated=False,
                links=build_async_job_links(
                    request,
                    job.id,
                    status_route="invoices-download-async-status",
                    stream_route="invoices-download-async-stream",
                    download_route="invoices-download-async-file",
                ),
            ),
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @extend_schema(
        parameters=[
            OpenApiParameter(
                "job_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True, description="Download job UUID"
            )
        ]
    )
    @extend_schema(
        parameters=[
            OpenApiParameter("job_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True),
        ]
    )
    def download_async_status(self, request, job_id: uuid.UUID | None = None):
        job = (
            restrict_to_owner_unless_privileged(
                InvoiceDownloadJob.objects.select_related("invoice").filter(id=job_id), request.user
            )
            .order_by("id")
            .first()
        )
        if not job:
            return self.error_response("Job not found", status.HTTP_404_NOT_FOUND)

        payload = {
            "jobId": str(job.id),
            "status": job.status,
            "progress": job.progress,
            "downloadUrl": request.build_absolute_uri(
                reverse("invoices-download-async-file", kwargs={"job_id": str(job.id)})
            ),
        }

        if job.status == InvoiceDownloadJob.STATUS_FAILED:
            payload["errorMessage"] = job.error_message or "Job failed"

        return Response(payload)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "job_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True, description="Download job UUID"
            )
        ]
    )
    @extend_schema(
        parameters=[
            OpenApiParameter("job_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True),
        ]
    )
    def download_async_stream(self, request, job_id: uuid.UUID | None = None):
        job = restrict_to_owner_unless_privileged(InvoiceDownloadJob.objects.filter(id=job_id), request.user).first()
        if not job:
            return self.error_response("Job not found", status.HTTP_404_NOT_FOUND)

        response = StreamingHttpResponse(
            self._stream_download_job(request, job, last_event_id=resolve_last_event_id(request)),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _stream_download_job(self, request, job, *, last_event_id: str | None = None):

        def _sync_stream():
            stream_key = stream_job_key(job.id)
            deadline = time.monotonic() + 55
            last_progress = None
            last_status = None
            initial_payload = _download_stream_payload_from_job(job)

            yield self._send_download_event(
                "start", {"message": "Starting invoice generation...", "progress": job.progress}
            )

            def _emit_updates(payload: dict[str, Any], *, event_id: str | None = None):
                nonlocal last_progress, last_status

                if last_progress != payload["progress"] or last_status != payload["status"]:
                    yield self._send_download_event(
                        "progress",
                        {"progress": payload["progress"], "status": payload["status"]},
                        event_id=event_id,
                    )
                    last_progress = payload["progress"]
                    last_status = payload["status"]

                if payload["status"] == InvoiceDownloadJob.STATUS_COMPLETED:
                    verified_payload = _load_download_stream_payload(job.id) or payload
                    yield self._send_download_event(
                        "complete",
                        {
                            "message": "Invoice ready",
                            "downloadUrl": request.build_absolute_uri(
                                reverse("invoices-download-async-file", kwargs={"job_id": str(job.id)})
                            ),
                            "status": verified_payload["status"],
                        },
                        event_id=event_id,
                    )
                    return

                if payload["status"] == InvoiceDownloadJob.STATUS_FAILED:
                    verified_payload = _load_download_stream_payload(job.id) or payload
                    yield self._send_download_event(
                        "error",
                        {
                            "message": verified_payload.get("errorMessage") or "Invoice generation failed",
                            "status": verified_payload["status"],
                        },
                        event_id=event_id,
                    )
                    return

            def _is_terminal_payload(payload: dict[str, Any]) -> bool:
                return payload["status"] in {
                    InvoiceDownloadJob.STATUS_COMPLETED,
                    InvoiceDownloadJob.STATUS_FAILED,
                }

            for chunk in _emit_updates(initial_payload):
                yield chunk
            if _is_terminal_payload(initial_payload):
                return

            for stream_event in iter_replay_and_live_events(
                stream_key=stream_key, last_event_id=last_event_id
            ):
                if time.monotonic() >= deadline:
                    return
                if stream_event is None:
                    yield ": keep-alive\n\n"
                    continue
                payload = normalize_invoice_download_job_payload(stream_event.payload)
                if payload is None or payload["status"] in {
                    InvoiceDownloadJob.STATUS_COMPLETED,
                    InvoiceDownloadJob.STATUS_FAILED,
                }:
                    payload = _load_download_stream_payload(job.id)
                    if payload is None:
                        yield self._send_download_event(
                            "error",
                            {"message": "Invoice generation failed", "status": InvoiceDownloadJob.STATUS_FAILED},
                            event_id=stream_event.id,
                        )
                        return
                done = False
                for chunk in _emit_updates(payload, event_id=stream_event.id):
                    yield chunk
                if _is_terminal_payload(payload):
                    return

        return _sync_stream()

    @staticmethod
    def _send_download_event(event_type, data, *, event_id: str | None = None):
        return format_sse_event(event=event_type, data=data, event_id=event_id)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "job_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True, description="Download job UUID"
            )
        ]
    )
    @extend_schema(
        parameters=[
            OpenApiParameter("job_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True),
        ]
    )
    def download_async_file(self, request, job_id: uuid.UUID | None = None):
        job = (
            restrict_to_owner_unless_privileged(
                InvoiceDownloadJob.objects.select_related("invoice", "invoice__customer").filter(id=job_id),
                request.user,
            )
            .order_by("id")
            .first()
        )
        if not job:
            return self.error_response("Job not found", status.HTTP_404_NOT_FOUND)

        if job.status != InvoiceDownloadJob.STATUS_COMPLETED or not job.output_path:
            return self.error_response("Job not completed yet", status.HTTP_400_BAD_REQUEST)

        invoice = job.invoice
        raw_name = f"{invoice.invoice_no_display}_{invoice.customer.full_name}"
        safe_name = slugify(raw_name, allow_unicode=False).replace("-", "_") or f"Invoice_{invoice.pk}"
        safe_name = safe_name[:200]
        extension = "pdf" if job.format_type == InvoiceDownloadJob.FORMAT_PDF else "docx"

        file_handle = default_storage.open(job.output_path, "rb")
        content_type = (
            "application/pdf"
            if extension == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        response = FileResponse(file_handle, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{safe_name}.{extension}"'
        return response

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="exclude_incomplete_document_collection",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="exclude_statuses",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="exclude_with_invoices",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="current_invoice_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
        ],
        responses=DocApplicationInvoiceSerializer(many=True),
    )
    @action(detail=False, methods=["get"], url_path="get_customer_applications/(?P<customer_id>[^/.]+)")
    def get_customer_applications(self, request, customer_id=None):
        if not customer_id:
            return self.error_response("Invalid request", status.HTTP_400_BAD_REQUEST)
        applications = (
            DocApplication.objects.filter(customer_id=customer_id)
            .filter(product__deprecated=False, product__uses_customer_app_workflow=True)
            .select_related("customer", "product")
            .prefetch_related("invoice_applications")
        )
        applications = applications.annotate(num_invoices=Count("invoice_applications"))

        exclude_incomplete_document_collection = (
            request.query_params.get("exclude_incomplete_document_collection", "true").lower() == "true"
        )
        exclude_statuses_string = request.query_params.get("exclude_statuses", None)
        if exclude_statuses_string:
            exclude_statuses = [status for status in exclude_statuses_string.split(",")]
            STATUS_DICT = dict(DocApplication.STATUS_CHOICES)
            if not all(status in STATUS_DICT.keys() for status in exclude_statuses):
                return self.error_response("Invalid status provided", status.HTTP_400_BAD_REQUEST)
        else:
            exclude_statuses = [DocApplication.STATUS_REJECTED]

        exclude_with_invoices = request.query_params.get("exclude_with_invoices", "true").lower() == "true"
        current_invoice_id = request.query_params.get("current_invoice_id")

        if exclude_incomplete_document_collection:
            applications = applications.filter_by_document_collection_completed()

        if exclude_statuses:
            applications = applications.exclude(status__in=exclude_statuses)

        if exclude_with_invoices:
            if current_invoice_id:
                applications = applications.exclude_already_invoiced(current_invoice_to_include=current_invoice_id)
            else:
                applications = applications.exclude(num_invoices__gt=0)

        page = self.paginate_queryset(applications)
        if page is not None:
            serializer = DocApplicationInvoiceSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = DocApplicationInvoiceSerializer(applications, many=True)
        return Response(serializer.data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="current_invoice_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Include already linked applications for this invoice in pending groups.",
            ),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=["get"], url_path="get_billable_products/(?P<customer_id>[^/.]+)")
    def get_billable_products(self, request, customer_id=None):
        if not customer_id:
            return self.error_response("Invalid request", status.HTTP_400_BAD_REQUEST)

        try:
            customer_id_value = int(customer_id)
        except (TypeError, ValueError):
            return self.error_response("Invalid customer id", status.HTTP_400_BAD_REQUEST)

        current_invoice_id = request.query_params.get("current_invoice_id")

        pending_applications = (
            DocApplication.objects.filter(
                customer_id=customer_id_value,
                product__deprecated=False,
                product__uses_customer_app_workflow=True,
            )
            .exclude(status=DocApplication.STATUS_REJECTED)
            .select_related("customer", "product")
            .prefetch_related("invoice_applications")
            .filter_by_document_collection_completed()
        )
        if current_invoice_id:
            pending_applications = pending_applications.exclude_already_invoiced(
                current_invoice_to_include=current_invoice_id
            )
        else:
            pending_applications = pending_applications.exclude(invoice_applications__isnull=False)
        pending_applications = pending_applications.order_by("-id").distinct()

        pending_by_product: dict[int, list[DocApplication]] = {}
        for application in pending_applications:
            pending_by_product.setdefault(application.product_id, []).append(application)

        products = Product.objects.filter(deprecated=False).order_by("name")
        response_rows = []
        for product in products:
            linked_apps = pending_by_product.get(product.id, [])
            response_rows.append(
                {
                    "product": ProductSerializer(product).data,
                    "pending_applications": DocApplicationInvoiceSerializer(linked_apps, many=True).data,
                    "pending_applications_count": len(linked_apps),
                    "has_pending_applications": bool(linked_apps),
                }
            )

        response_rows.sort(
            key=lambda row: (
                0 if row["has_pending_applications"] else 1,
                (row["product"].get("name") or "").lower(),
            )
        )
        return Response(response_rows)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="application_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                required=True,
            ),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=["get"], url_path="from_application_prefill/(?P<application_id>[^/.]+)")
    def from_application_prefill(self, request, application_id=None):
        if not application_id:
            return self.error_response("Invalid request", status.HTTP_400_BAD_REQUEST)
        try:
            source_application_id = int(application_id)
        except (TypeError, ValueError):
            return self.error_response("Invalid application id", status.HTTP_400_BAD_REQUEST)

        source_application = (
            DocApplication.objects.select_related("customer", "product")
            .prefetch_related("invoice_applications")
            .filter(id=source_application_id)
            .first()
        )
        if not source_application:
            return self.error_response("Customer application not found.", status.HTTP_404_NOT_FOUND)

        product = source_application.product
        if not product or product.deprecated:
            return self.error_response("Source application product is not billable.", status.HTTP_400_BAD_REQUEST)
        if not product.uses_customer_app_workflow:
            return self.error_response(
                "Source application product is invoice-only and cannot be invoiced from customer applications.",
                status.HTTP_400_BAD_REQUEST,
            )
        if source_application.invoice_applications.exists():
            return self.error_response(
                "This customer application is already invoiced.",
                status.HTTP_400_BAD_REQUEST,
            )

        amount = product.retail_price if product.retail_price is not None else product.base_price or 0

        return Response(
            build_success_payload(
                {
                    "customer": CustomerSerializer(source_application.customer).data,
                    "sourceApplication": DocApplicationInvoiceSerializer(source_application).data,
                    "invoiceApplication": {
                        "product": product.id,
                        "customerApplication": source_application.id,
                        "amount": str(amount),
                    },
                    "locks": {
                        "customer": True,
                        "sourceLine": True,
                    },
                },
                request=request,
            )
        )

    @action(
        detail=False, methods=["get"], url_path="get_invoice_application_due_amount/(?P<invoice_application_id>[^/.]+)"
    )
    def get_invoice_application_due_amount(self, request, invoice_application_id=None):
        if not invoice_application_id:
            return self.error_response("Invalid request", status.HTTP_400_BAD_REQUEST)
        try:
            invoice_application = InvoiceApplication.objects.get(pk=invoice_application_id)
        except InvoiceApplication.DoesNotExist:
            return self.error_response("Invoice Application does not exist", status.HTTP_404_NOT_FOUND)
        return Response(
            build_success_payload(
                {
                    "dueAmount": str(invoice_application.due_amount),
                    "amount": str(invoice_application.amount),
                    "paidAmount": str(invoice_application.paid_amount),
                },
                request=request,
            )
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="invoice_date",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
            )
        ]
    )
    @action(detail=False, methods=["get"], url_path="propose", url_name="propose")
    def propose_invoice(self, request):
        """Propose the next available invoice number for a given invoice_date."""
        invoice_date = request.query_params.get("invoice_date")
        year = None
        if invoice_date:
            try:
                # Expect YYYY-MM-DD
                year = datetime.fromisoformat(invoice_date).year
            except Exception:
                try:
                    # try parsing date string fallback
                    year = datetime.strptime(invoice_date, "%Y-%m-%d").year
                except Exception:
                    year = None
        if year is None:
            year = timezone.now().year

        proposed = Invoice.get_next_invoice_no_for_year(year)
        return Response(build_success_payload({"invoiceNo": proposed}, request=request))

    @extend_schema(request=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="mark-as-paid")
    def mark_as_paid(self, request, pk=None):
        invoice = self.get_object()
        payment_type = request.data.get("payment_type")
        payment_date = request.data.get("payment_date")
        if not payment_type:
            return self.error_response("Payment type is required", status.HTTP_400_BAD_REQUEST)

        parsed_date = None
        if payment_date:
            try:
                parsed_date = datetime.strptime(payment_date, "%Y-%m-%d").date()
            except ValueError:
                return self.error_response("Invalid payment date format", status.HTTP_400_BAD_REQUEST)

        from core.services.invoice_service import mark_invoice_as_paid

        created = mark_invoice_as_paid(
            invoice=invoice,
            payment_type=payment_type,
            payment_date=parsed_date,
            user=request.user,
        )
        return Response(
            build_success_payload({"created": len(created)}, request=request),
            status=status.HTTP_201_CREATED,
        )

    # --------------------------------------------------------------------- #
    # Invoice Import Endpoints                                               #
    # --------------------------------------------------------------------- #

    @extend_schema(
        responses=OpenApiTypes.OBJECT,
        description="Get LLM configuration and supported formats for invoice import.",
    )
    @action(detail=False, methods=["get"], url_path="import/config")
    def import_config(self, request):
        """Return LLM configuration and import settings."""
        from core.services.ai_runtime_settings_service import AIRuntimeSettingsService
        from django.conf import settings as django_settings

        llm_config = AIRuntimeSettingsService.get_model_catalog()
        runtime_settings = AIRuntimeSettingsService.get_many()

        return Response(
            {
                "providers": llm_config.get("providers", {}),
                "currentProvider": AIRuntimeSettingsService.get_llm_provider(),
                "currentModel": AIRuntimeSettingsService.get_llm_default_model(),
                "runtimeSettings": runtime_settings,
                "maxWorkers": AppSettingService.parse_int(
                    AppSettingService.get_effective_raw("INVOICE_IMPORT_MAX_WORKERS", 3), 3
                ),
                "supportedFormats": [".pdf", ".xlsx", ".xls", ".docx", ".doc"],
            }
        )

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "binary"},
                    "llm_provider": {"type": "string"},
                    "llm_model": {"type": "string"},
                },
                "required": ["file"],
            }
        },
        responses=OpenApiTypes.OBJECT,
        description="Import a single invoice file using AI parsing.",
    )
    @action(detail=False, methods=["post"], url_path="import/single", parser_classes=[MultiPartParser, FormParser])
    def import_single(self, request):
        """Process single uploaded invoice file."""
        if "file" not in request.FILES:
            return self.error_response("No file uploaded", status.HTTP_400_BAD_REQUEST)

        uploaded_file = request.FILES["file"]
        llm_provider = request.POST.get("llm_provider") or request.data.get("llmProvider")
        llm_model = request.POST.get("llm_model") or request.data.get("llmModel")

        # Validate file extension
        allowed_extensions = [".pdf", ".xlsx", ".xls", ".docx", ".doc"]
        file_ext = uploaded_file.name.lower().split(".")[-1]
        if f".{file_ext}" not in allowed_extensions:
            return self.error_response(
                f"Unsupported file format: .{file_ext}",
                status.HTTP_400_BAD_REQUEST,
                details={"filename": uploaded_file.name},
            )

        try:
            from invoices.services.invoice_importer import InvoiceImporter

            importer = InvoiceImporter(user=request.user, llm_provider=llm_provider, llm_model=llm_model)
            result = importer.import_from_file(uploaded_file, uploaded_file.name)

            response_data = {
                "success": result.success,
                "status": result.status,
                "message": result.message,
                "filename": uploaded_file.name,
            }

            if result.invoice:
                response_data["invoice"] = {
                    "id": result.invoice.pk,
                    "invoiceNo": result.invoice.invoice_no_display,
                    "customerName": result.invoice.customer.full_name,
                    "totalAmount": str(result.invoice.total_amount),
                    "invoiceDate": result.invoice.invoice_date.strftime("%Y-%m-%d"),
                    "status": result.invoice.get_status_display(),
                }

            if result.customer:
                response_data["customer"] = {
                    "id": result.customer.pk,
                    "title": result.customer.title or "",
                    "name": result.customer.full_name,
                    "email": result.customer.email or "",
                    "phone": result.customer.telephone or "",
                    "address": result.customer.address_bali or "",
                    "company": result.customer.company_name or "",
                    "npwp": result.customer.npwp or "",
                }

            if result.errors:
                response_data["errors"] = result.errors

            status_code = 200 if result.success else (409 if result.status == "duplicate" else 400)
            return Response(response_data, status=status_code)

        except Exception as e:
            logger.exception("Error processing invoice import upload")
            return self.error_response(
                "Server error while processing invoice import.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"filename": uploaded_file.name},
            )

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "files": {"type": "array", "items": {"type": "string", "format": "binary"}},
                    "paid_status": {"type": "array", "items": {"type": "string"}},
                    "llm_provider": {"type": "string"},
                    "llm_model": {"type": "string"},
                },
                "required": ["files"],
            }
        },
        responses=OpenApiTypes.OBJECT,
        description="Import multiple invoice files with SSE progress streaming.",
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="import/batch",
        parser_classes=[MultiPartParser, FormParser],
        throttle_scope="invoice_import_batch",
        throttle_classes=[AnonRateThrottle, UserRateThrottle, ScopedRateThrottle],
    )
    def import_batch(self, request):
        """Process multiple uploaded invoice files with real-time progress streaming."""
        from django.utils.text import get_valid_filename
        from invoices.models import InvoiceImportItem, InvoiceImportJob
        from invoices.tasks.import_jobs import run_invoice_import_item

        namespace = "invoice_import_batch"
        request_fingerprint = build_request_idempotency_fingerprint(request)
        idempotency_cache_key, cached_job = resolve_request_idempotent_job(
            request=request,
            namespace=namespace,
            user_id=request.user.id,
            queryset=InvoiceImportJob.objects.filter(created_by=request.user),
            fingerprint=request_fingerprint,
        )
        if cached_job is not None:
            response = StreamingHttpResponse(
                self._stream_import_job(cached_job.id, request),
                content_type="text/event-stream",
            )
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"
            return response

        files = request.FILES.getlist("files")
        paid_status_list = request.POST.getlist("paid_status") or request.data.getlist("paidStatus")
        llm_provider = request.POST.get("llm_provider") or request.data.get("llmProvider")
        llm_model = request.POST.get("llm_model") or request.data.get("llmModel")

        if not files:
            return self.error_response("No files uploaded", status.HTTP_400_BAD_REQUEST)

        def build_existing_stream(existing_job):
            response = StreamingHttpResponse(
                self._stream_import_job(existing_job.id, request),
                content_type="text/event-stream",
            )
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"
            return response

        guard = prepare_async_enqueue(
            namespace=namespace,
            user=request.user,
            inflight_queryset=InvoiceImportJob.objects.filter(created_by=request.user),
            inflight_statuses=QUEUE_JOB_INFLIGHT_STATUSES,
            busy_message="Invoice import trigger is already being processed. Please retry in a moment.",
            deduplicated_response_builder=build_existing_stream,
            error_response_builder=self.error_response,
        )
        if guard.response is not None:
            return guard.response

        lock_key = guard.lock_key
        lock_token = guard.lock_token
        try:
            job = InvoiceImportJob.objects.create(
                status=InvoiceImportJob.STATUS_QUEUED,
                progress=0,
                total_files=len(files),
                created_by=request.user,
                request_params={"llm_provider": llm_provider, "llm_model": llm_model},
            )
            store_request_idempotent_job(
                cache_key=idempotency_cache_key,
                job_id=job.id,
                fingerprint=request_fingerprint,
            )

            for index, uploaded_file in enumerate(files, 1):
                filename = uploaded_file.name
                is_paid = paid_status_list[index - 1].lower() == "true" if index - 1 < len(paid_status_list) else False
                safe_name = get_valid_filename(os.path.basename(filename))
                tmp_dir = os.path.join(getattr(settings, "TMPFILES_FOLDER", "tmpfiles"), "invoice_imports", str(job.id))
                tmp_path = os.path.join(tmp_dir, safe_name)
                file_path = default_storage.save(tmp_path, uploaded_file)

                item = InvoiceImportItem.objects.create(
                    job=job,
                    sort_index=index,
                    filename=filename,
                    file_path=file_path,
                    is_paid=is_paid,
                    status=InvoiceImportItem.STATUS_QUEUED,
                )
                run_invoice_import_item(str(item.id))
        finally:
            if lock_key and lock_token:
                release_enqueue_guard(lock_key, lock_token)

        # Return SSE stream
        response = StreamingHttpResponse(
            self._stream_import_job(job.id, request),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    @extend_schema(
        responses=OpenApiTypes.OBJECT,
        description="Get status of an invoice import job.",
    )
    @extend_schema(
        parameters=[
            OpenApiParameter(
                "job_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True, description="Import job UUID"
            )
        ]
    )
    @extend_schema(
        parameters=[
            OpenApiParameter("job_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True),
        ]
    )
    def import_job_status(self, request, job_id: uuid.UUID | None = None):
        """Get status of an import job."""
        from invoices.models import InvoiceImportJob

        job = restrict_to_owner_unless_privileged(InvoiceImportJob.objects.filter(id=job_id), request.user).first()
        if not job:
            return self.error_response("Job not found", status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "jobId": str(job.id),
                "status": job.status,
                "progress": job.progress,
                "totalFiles": job.total_files,
                "processedFiles": job.processed_files,
                "importedCount": job.imported_count,
                "duplicateCount": job.duplicate_count,
                "errorCount": job.error_count,
            }
        )

    @extend_schema(
        parameters=[
            OpenApiParameter("job_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True),
        ]
    )
    @action(detail=False, methods=["get"], url_path=r"import/stream/(?P<job_id>[^/.]+)")
    def import_job_stream(self, request, job_id=None):
        """Stream SSE updates for a running import job."""
        from invoices.models import InvoiceImportJob

        job = restrict_to_owner_unless_privileged(InvoiceImportJob.objects.filter(id=job_id), request.user).first()
        if not job:
            return self.error_response("Job not found", status.HTTP_404_NOT_FOUND)

        response = StreamingHttpResponse(
            self._stream_import_job(job.id, request, last_event_id=resolve_last_event_id(request)),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _stream_import_job(self, job_id, request=None, *, last_event_id: str | None = None):
        """Stream SSE updates for a running import job."""
        from invoices.models import InvoiceImportItem, InvoiceImportJob

        def _sync_stream():
            stream_key = stream_job_key(job_id)
            deadline = time.monotonic() + 55
            sent_states: dict[str, dict[str, bool]] = {}
            job = InvoiceImportJob.objects.prefetch_related("items").get(id=job_id)
            job_state = _import_job_stream_payload_from_job(job)
            ordered_items = list(job.items.all().order_by("sort_index"))
            item_order = [str(item.id) for item in ordered_items]
            item_states = {str(item.id): _import_item_stream_payload_from_item(item) for item in ordered_items}
            total_files = job_state["totalFiles"]

            yield self._send_import_event(
                "start",
                {
                    "total": total_files,
                    "message": f"Starting background import of {total_files} file(s)...",
                },
            )

            terminal_statuses = {
                InvoiceImportJob.STATUS_COMPLETED,
                InvoiceImportJob.STATUS_FAILED,
            }
            terminal_item_statuses = {
                InvoiceImportItem.STATUS_IMPORTED,
                InvoiceImportItem.STATUS_DUPLICATE,
                InvoiceImportItem.STATUS_ERROR,
            }

            def _refresh_job_state_from_db() -> None:
                nonlocal job_state
                refreshed_job = InvoiceImportJob.objects.get(id=job_id)
                job_state = _import_job_stream_payload_from_job(refreshed_job)

            def _refresh_item_state_from_db(raw_item_id: str | None) -> str | None:
                if not raw_item_id:
                    return None
                try:
                    refreshed_item = InvoiceImportItem.objects.get(id=raw_item_id)
                except InvoiceImportItem.DoesNotExist:
                    return None
                normalized_item = _import_item_stream_payload_from_item(refreshed_item)
                item_id = normalized_item["itemId"]
                item_states[item_id] = normalized_item
                if item_id not in item_order:
                    item_order.append(item_id)
                return item_id

            def _build_import_result_from_state(item_state: dict[str, Any]) -> dict[str, Any]:
                result = item_state.get("result")
                if isinstance(result, dict) and result.get("status"):
                    return result
                return {
                    "success": item_state.get("status") == InvoiceImportItem.STATUS_IMPORTED,
                    "status": item_state.get("status"),
                    "message": item_state.get("errorMessage") or "Processing",
                    "filename": item_state.get("filename"),
                }

            def _build_import_summary_from_state() -> dict[str, Any]:
                results = [_build_import_result_from_state(item_states[item_id]) for item_id in item_order]
                summary = {
                    "total": job_state["totalFiles"],
                    "imported": job_state["importedCount"],
                    "duplicates": job_state["duplicateCount"],
                    "errors": job_state["errorCount"],
                }
                return {"summary": summary, "results": results}

            def _collect_updates(
                *,
                event_id: str | None = None,
                changed_item_ids: set[str] | None = None,
            ) -> tuple[list[str], bool]:
                messages: list[str] = []
                item_ids = (
                    item_order
                    if changed_item_ids is None
                    else [item_id for item_id in item_order if item_id in changed_item_ids]
                )

                for item_id in item_ids:
                    item = item_states[item_id]

                    state = sent_states.get(item_id, {"file_start": False, "parsing": False, "done": False})

                    if item["status"] == InvoiceImportItem.STATUS_PROCESSING and not state["file_start"]:
                        messages.append(
                            self._send_import_event(
                                "file_start",
                                {
                                    "index": item["index"],
                                    "filename": item["filename"],
                                    "message": f"Processing {item['filename']}...",
                                },
                                event_id=event_id,
                            )
                        )
                        state["file_start"] = True

                    if (
                        item["status"] == InvoiceImportItem.STATUS_PROCESSING
                        and isinstance(item.get("result"), dict)
                        and item["result"].get("stage") == "parsing"
                        and not state["parsing"]
                    ):
                        messages.append(
                            self._send_import_event(
                                "parsing",
                                {
                                    "index": item["index"],
                                    "filename": item["filename"],
                                    "message": f"Parsing {item['filename']} with AI...",
                                },
                                event_id=event_id,
                            )
                        )
                        state["parsing"] = True

                    if item["status"] in terminal_item_statuses and not state["done"]:
                        result_data = _build_import_result_from_state(item)
                        if item["status"] == InvoiceImportItem.STATUS_IMPORTED:
                            event_type = "file_success"
                            message = f"✓ Successfully imported {item['filename']}"
                        elif item["status"] == InvoiceImportItem.STATUS_DUPLICATE:
                            event_type = "file_duplicate"
                            message = f"⚠ Duplicate invoice detected: {item['filename']}"
                        else:
                            event_type = "file_error"
                            message = (
                                f"✗ Error processing {item['filename']}: {result_data.get('message', 'Unknown error')}"
                            )

                        messages.append(
                            self._send_import_event(
                                event_type,
                                {
                                    "index": item["index"],
                                    "filename": item["filename"],
                                    "message": message,
                                    "result": result_data,
                                },
                                event_id=event_id,
                            )
                        )
                        state["done"] = True

                    sent_states[item_id] = state

                if (
                    job_state["status"] in terminal_statuses
                    and job_state["processedFiles"] >= job_state["totalFiles"]
                    and all(item_states[item_id]["status"] in terminal_item_statuses for item_id in item_order)
                ):
                    summary = _build_import_summary_from_state()
                    messages.append(
                        self._send_import_event(
                            "complete",
                            {
                                "message": f"Import complete: {summary['summary']['imported']} imported, "
                                f"{summary['summary']['duplicates']} duplicates, {summary['summary']['errors']} errors",
                                **summary,
                            },
                            event_id=event_id,
                        )
                    )
                    return messages, True
                return messages, False

            initial_messages, done = _collect_updates()
            for message in initial_messages:
                yield message
            if done:
                return

            for stream_event in iter_replay_and_live_events(
                stream_key=stream_key, last_event_id=last_event_id
            ):
                if time.monotonic() >= deadline:
                    return
                if stream_event is None:
                    yield ": keep-alive\n\n"
                    continue

                changed_ids: set[str] | None = None
                if stream_event.event == "invoice_import_job_changed":
                    payload = normalize_invoice_import_job_payload(stream_event.payload)
                    if payload is None:
                        _refresh_job_state_from_db()
                    else:
                        job_state = payload
                    changed_ids = None
                elif stream_event.event == "invoice_import_item_changed":
                    payload = normalize_invoice_import_item_payload(stream_event.payload)
                    if payload is None:
                        raw_item_id = first_present(stream_event.payload, "itemId", "item_id")
                        refreshed_item_id = _refresh_item_state_from_db(str(raw_item_id) if raw_item_id else None)
                        changed_ids = {refreshed_item_id} if refreshed_item_id else None
                    else:
                        item_id = payload["itemId"]
                        item_states[item_id] = payload
                        if item_id not in item_order:
                            item_order.append(item_id)
                        changed_ids = {item_id}
                else:
                    _refresh_job_state_from_db()
                    changed_ids = None

                messages, done = _collect_updates(event_id=stream_event.id, changed_item_ids=changed_ids)
                for message in messages:
                    yield message
                if done:
                    return

        return _sync_stream()

    @staticmethod
    def _send_import_event(event_type, data, *, event_id: str | None = None):
        """Format and send an SSE event."""
        return format_sse_event(event=event_type, data=data, event_id=event_id)


class PaymentViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = Payment.objects.select_related(
            "invoice_application",
            "invoice_application__invoice",
            "from_customer",
        )

        invoice_application_id = self.request.query_params.get("invoice_application_id")
        if invoice_application_id:
            queryset = queryset.filter(invoice_application_id=invoice_application_id)
        return queryset

    def perform_create(self, serializer):
        from core.services.invoice_service import create_payment

        invoice_application = serializer.validated_data.get("invoice_application")
        if not invoice_application:
            raise ValidationError("invoice_application is required")

        payment = create_payment(
            invoice_application=invoice_application,
            amount=serializer.validated_data.get("amount"),
            payment_type=serializer.validated_data.get("payment_type"),
            payment_date=serializer.validated_data.get("payment_date"),
            user=self.request.user,
            notes=serializer.validated_data.get("notes"),
        )
        serializer.instance = payment

    def perform_update(self, serializer):
        from core.services.invoice_service import update_payment

        payment = update_payment(
            payment=self.get_object(),
            amount=serializer.validated_data.get("amount"),
            payment_type=serializer.validated_data.get("payment_type"),
            payment_date=serializer.validated_data.get("payment_date"),
            user=self.request.user,
            notes=serializer.validated_data.get("notes"),
        )
        serializer.instance = payment
