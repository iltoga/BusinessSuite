from .views_imports import *

class InvoiceViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    throttle_scope = None
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
        if not is_superuser(request.user):
            return self.error_response("Only superusers can delete invoices.", status.HTTP_403_FORBIDDEN)

        invoice = self.get_object()

        from invoices.services.invoice_deletion import build_invoice_delete_preview

        preview = build_invoice_delete_preview(invoice)

        return Response(
            {
                "invoice_no_display": invoice.invoice_no_display,
                "customer_name": invoice.customer.full_name,
                "total_amount": invoice.total_amount,
                "status_display": invoice.get_status_display(),
                "invoice_applications_count": preview.invoice_applications_count,
                "customer_applications_count": preview.customer_applications_count,
                "payments_count": preview.payments_count,
            }
        )

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="force-delete")
    def force_delete(self, request, pk=None):
        if not is_superuser(request.user):
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

        return Response({"deleted": True, **result})

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        if not is_superuser(request.user):
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

        return Response(result)

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
        format_type = (
            request.data.get("file_format")
            or request.data.get("format")
            or request.query_params.get("file_format")
            or "pdf"
        ).lower()

        if format_type not in [InvoiceDownloadJob.FORMAT_DOCX, InvoiceDownloadJob.FORMAT_PDF]:
            return self.error_response("Invalid format. Use 'docx' or 'pdf'.", status.HTTP_400_BAD_REQUEST)

        invoice = self.get_object()
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
                {
                    "job_id": str(existing_job.id),
                    "status": existing_job.status,
                    "progress": existing_job.progress,
                    "status_url": request.build_absolute_uri(
                        reverse("invoices-download-async-status", kwargs={"job_id": str(existing_job.id)})
                    ),
                    "stream_url": request.build_absolute_uri(
                        reverse("invoices-download-async-stream", kwargs={"job_id": str(existing_job.id)})
                    ),
                    "download_url": request.build_absolute_uri(
                        reverse("invoices-download-async-file", kwargs={"job_id": str(existing_job.id)})
                    ),
                    "queued": False,
                    "deduplicated": True,
                },
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
        finally:
            if lock_key and lock_token:
                release_enqueue_guard(lock_key, lock_token)

        return Response(
            {
                "job_id": str(job.id),
                "status": job.status,
                "progress": job.progress,
                "status_url": request.build_absolute_uri(
                    reverse("invoices-download-async-status", kwargs={"job_id": str(job.id)})
                ),
                "stream_url": request.build_absolute_uri(
                    reverse("invoices-download-async-stream", kwargs={"job_id": str(job.id)})
                ),
                "download_url": request.build_absolute_uri(
                    reverse("invoices-download-async-file", kwargs={"job_id": str(job.id)})
                ),
                "queued": True,
                "deduplicated": False,
            },
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
            "job_id": str(job.id),
            "status": job.status,
            "progress": job.progress,
            "download_url": request.build_absolute_uri(
                reverse("invoices-download-async-file", kwargs={"job_id": str(job.id)})
            ),
        }

        if job.status == InvoiceDownloadJob.STATUS_FAILED:
            payload["error"] = job.error_message or "Job failed"

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
        stream_key = stream_job_key(job.id)
        last_progress = None
        last_status = None

        yield self._send_download_event(
            "start", {"message": "Starting invoice generation...", "progress": job.progress}
        )

        def _emit_updates(*, event_id: str | None = None) -> Generator[str, None, bool]:
            nonlocal last_progress
            nonlocal last_status
            job.refresh_from_db()

            if last_progress != job.progress or last_status != job.status:
                yield self._send_download_event(
                    "progress",
                    {"progress": job.progress, "status": job.status},
                    event_id=event_id,
                )
                last_progress = job.progress
                last_status = job.status

            if job.status == InvoiceDownloadJob.STATUS_COMPLETED:
                yield self._send_download_event(
                    "complete",
                    {
                        "message": "Invoice ready",
                        "download_url": request.build_absolute_uri(
                            reverse("invoices-download-async-file", kwargs={"job_id": str(job.id)})
                        ),
                        "status": job.status,
                    },
                    event_id=event_id,
                )
                return True

            if job.status == InvoiceDownloadJob.STATUS_FAILED:
                yield self._send_download_event(
                    "error",
                    {"message": job.error_message or "Invoice generation failed", "status": job.status},
                    event_id=event_id,
                )
                return True
            return False

        done = yield from _emit_updates()
        if done:
            return

        for stream_event in iter_replay_and_live_events(stream_key=stream_key, last_event_id=last_event_id):
            if stream_event is None:
                yield ": keep-alive\n\n"
                continue
            done = yield from _emit_updates(event_id=stream_event.id)
            if done:
                return

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
            {
                "customer": CustomerSerializer(source_application.customer).data,
                "source_application": DocApplicationInvoiceSerializer(source_application).data,
                "invoice_application": {
                    "product": product.id,
                    "customer_application": source_application.id,
                    "amount": str(amount),
                },
                "locks": {
                    "customer": True,
                    "source_line": True,
                },
            }
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
            {
                "due_amount": str(invoice_application.due_amount),
                "amount": str(invoice_application.amount),
                "paid_amount": str(invoice_application.paid_amount),
            }
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
        return Response({"invoice_no": proposed, "invoiceNo": proposed})

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
        return Response({"created": len(created)}, status=status.HTTP_201_CREATED)

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
        import json as json_module

        from django.conf import settings as django_settings
        from django.contrib.staticfiles import finders

        # Load LLM models config from static file
        llm_config = {"providers": {}}
        llm_config_path = finders.find("llm_models.json")
        if not llm_config_path:
            llm_config_path = django_settings.BASE_DIR / "business_suite" / "static" / "llm_models.json"

        try:
            with open(llm_config_path, "r") as f:
                llm_config = json_module.load(f)
        except Exception:
            llm_config = {"providers": {}}

        return Response(
            {
                "providers": llm_config.get("providers", {}),
                "currentProvider": getattr(django_settings, "LLM_PROVIDER", "openrouter"),
                "currentModel": getattr(django_settings, "LLM_DEFAULT_MODEL", "google/gemini-2.5-flash-lite"),
                "maxWorkers": getattr(django_settings, "INVOICE_IMPORT_MAX_WORKERS", 3),
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
        from invoices.models import InvoiceImportJob

        stream_key = stream_job_key(job_id)
        sent_states = {}
        job = InvoiceImportJob.objects.get(id=job_id)
        total_files = job.total_files

        yield self._send_import_event(
            "start",
            {
                "total": total_files,
                "message": f"Starting background import of {total_files} file(s)...",
            },
        )

        def _collect_updates(
            *,
            event_id: str | None = None,
            changed_item_ids: set[int] | None = None,
        ) -> tuple[list[str], bool]:
            messages: list[str] = []
            job.refresh_from_db()
            if changed_item_ids is None:
                items = list(job.items.all().order_by("sort_index"))
            elif changed_item_ids:
                items = list(job.items.filter(id__in=changed_item_ids).order_by("sort_index"))
            else:
                items = []

            for item in items:
                from invoices.models import InvoiceImportItem

                state = sent_states.get(item.id, {"file_start": False, "parsing": False, "done": False})

                if item.status == InvoiceImportItem.STATUS_PROCESSING and not state["file_start"]:
                    messages.append(
                        self._send_import_event(
                            "file_start",
                            {
                                "index": item.sort_index,
                                "filename": item.filename,
                                "message": f"Processing {item.filename}...",
                            },
                            event_id=event_id,
                        )
                    )
                    state["file_start"] = True

                if (
                    item.status == InvoiceImportItem.STATUS_PROCESSING
                    and item.result
                    and item.result.get("stage") == "parsing"
                    and not state["parsing"]
                ):
                    messages.append(
                        self._send_import_event(
                            "parsing",
                            {
                                "index": item.sort_index,
                                "filename": item.filename,
                                "message": f"Parsing {item.filename} with AI...",
                            },
                            event_id=event_id,
                        )
                    )
                    state["parsing"] = True

                if (
                    item.status
                    in [
                        InvoiceImportItem.STATUS_IMPORTED,
                        InvoiceImportItem.STATUS_DUPLICATE,
                        InvoiceImportItem.STATUS_ERROR,
                    ]
                    and not state["done"]
                ):
                    result_data = self._build_import_result(item)
                    if item.status == InvoiceImportItem.STATUS_IMPORTED:
                        event_type = "file_success"
                        message = f"✓ Successfully imported {item.filename}"
                    elif item.status == InvoiceImportItem.STATUS_DUPLICATE:
                        event_type = "file_duplicate"
                        message = f"⚠ Duplicate invoice detected: {item.filename}"
                    else:
                        event_type = "file_error"
                        message = f"✗ Error processing {item.filename}: {result_data.get('message', 'Unknown error')}"

                    messages.append(
                        self._send_import_event(
                            event_type,
                            {
                                "index": item.sort_index,
                                "filename": item.filename,
                                "message": message,
                                "result": result_data,
                            },
                            event_id=event_id,
                        )
                    )
                    state["done"] = True

                sent_states[item.id] = state

            if (
                job.processed_files >= job.total_files
                and len(sent_states) >= job.total_files
                and all(state["done"] for state in sent_states.values())
            ):
                summary_items = items if changed_item_ids is None else list(job.items.all().order_by("sort_index"))
                summary = self._build_import_summary(job, summary_items)
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

        def _parse_changed_item_id(stream_event) -> int | None:
            if stream_event.event != "invoice_import_item_changed":
                return None
            payload = stream_event.payload if isinstance(stream_event.payload, dict) else {}
            raw_item_id = payload.get("itemId")
            try:
                return int(raw_item_id)
            except (TypeError, ValueError):
                return None

        initial_messages, done = _collect_updates()
        for message in initial_messages:
            yield message
        if done:
            return

        refresh_interval_seconds = 0.35
        full_refresh_interval_seconds = 3.0
        last_refresh_at = time.monotonic()
        last_full_refresh_at = time.monotonic()
        pending_event_id: str | None = None
        pending_item_ids: set[int] = set()
        force_full_refresh = False

        for stream_event in iter_replay_and_live_events(stream_key=stream_key, last_event_id=last_event_id):
            if stream_event is None:
                if pending_event_id is not None:
                    should_full_refresh = force_full_refresh or (
                        time.monotonic() - last_full_refresh_at >= full_refresh_interval_seconds
                    )
                    changed_ids = None if should_full_refresh else set(pending_item_ids)
                    messages, done = _collect_updates(event_id=pending_event_id, changed_item_ids=changed_ids)
                    pending_event_id = None
                    pending_item_ids.clear()
                    force_full_refresh = False
                    if changed_ids is None:
                        last_full_refresh_at = time.monotonic()
                    last_refresh_at = time.monotonic()
                    for message in messages:
                        yield message
                    if done:
                        return
                yield ": keep-alive\n\n"
                continue

            pending_event_id = stream_event.id
            changed_item_id = _parse_changed_item_id(stream_event)
            if changed_item_id is not None:
                pending_item_ids.add(changed_item_id)
            elif stream_event.event != "invoice_import_job_changed":
                force_full_refresh = True
            now = time.monotonic()
            if (
                now - last_refresh_at
            ) < refresh_interval_seconds and stream_event.event != "invoice_import_job_changed":
                continue

            should_full_refresh = force_full_refresh or (now - last_full_refresh_at >= full_refresh_interval_seconds)
            changed_ids = None if should_full_refresh else set(pending_item_ids)
            messages, done = _collect_updates(event_id=pending_event_id, changed_item_ids=changed_ids)
            pending_event_id = None
            pending_item_ids.clear()
            force_full_refresh = False
            if changed_ids is None:
                last_full_refresh_at = now
            last_refresh_at = now
            for message in messages:
                yield message
            if done:
                return

        if pending_event_id is not None:
            should_full_refresh = force_full_refresh or (
                time.monotonic() - last_full_refresh_at >= full_refresh_interval_seconds
            )
            changed_ids = None if should_full_refresh else set(pending_item_ids)
            messages, done = _collect_updates(event_id=pending_event_id, changed_item_ids=changed_ids)
            for message in messages:
                yield message
            if done:
                return

    def _build_import_result(self, item):
        """Build result data for an import item."""
        if item.result and isinstance(item.result, dict) and item.result.get("status"):
            return item.result
        return {
            "success": item.status == "imported",
            "status": item.status,
            "message": item.error_message or "Processing",
            "filename": item.filename,
        }

    def _build_import_summary(self, job, items):
        """Build summary for completed import job."""
        results = [self._build_import_result(item) for item in items]
        summary = {
            "total": job.total_files,
            "imported": job.imported_count,
            "duplicates": job.duplicate_count,
            "errors": job.error_count,
        }
        return {"summary": summary, "results": results}

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
