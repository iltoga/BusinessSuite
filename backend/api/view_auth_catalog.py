from .views_imports import *

class TokenAuthView(TokenObtainPairView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainSerializer


class UserProfileViewSet(ApiErrorHandlingMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(responses={200: UserProfileSerializer})
    @action(detail=False, methods=["get"])
    def me(self, request):
        """Retrieve current user profile."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def logout(self, request):
        """Logout current user and record it in Django."""
        django_logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=UserProfileSerializer, responses={200: UserProfileSerializer})
    @action(detail=False, methods=["patch"], url_path="update_profile")
    def update_profile(self, request):
        serializer = self.get_serializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"avatar": {"type": "string", "format": "binary"}},
                "required": ["avatar"],
            },
        },
        responses={200: UserProfileSerializer},
    )
    @action(detail=False, methods=["post"], url_path="upload_avatar")
    def upload_avatar(self, request):
        """Upload user profile picture."""
        serializer = AvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        profile, _ = UserProfile.objects.get_or_create(user=user)

        validated_data = serializer.validated_data
        if validated_data is not None:
            profile.avatar = validated_data.get("avatar")
        profile.save()

        serializer = self.get_serializer(user)
        return Response(serializer.data)

    @extend_schema(
        request=ChangePasswordSerializer, responses={204: OpenApiResponse(description="Password updated successfully")}
    )
    @action(detail=False, methods=["post"], url_path="change_password")
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        # Ensure we have a valid dict and handle the subscripting safely for Pylance
        validated_data = serializer.validated_data
        if validated_data is not None:
            request.user.set_password(validated_data.get("new_password"))
            request.user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserSettingsViewSet(ApiErrorHandlingMixin, viewsets.GenericViewSet):
    """ViewSet to manage per-user settings (theme, dark_mode, preferences)."""

    permission_classes = [IsAuthenticated]
    serializer_class = UserSettingsSerializer

    @extend_schema(request=UserSettingsSerializer, responses={200: UserSettingsSerializer})
    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        """Retrieve or partially update current user's settings.

        Supports GET and PATCH on the same URL `/me/`.
        """
        settings_obj, _ = UserSettings.objects.get_or_create(user=request.user)

        if request.method == "GET":
            serializer = self.get_serializer(settings_obj)
            return Response(serializer.data)

        # PATCH
        serializer = self.get_serializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CountryCodeViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = CountryCode.objects.all()
    serializer_class = CountryCodeSerializer
    pagination_class = None  # No pagination for country list as it's small and used for dropdowns
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["country", "country_idn", "alpha3_code"]
    ordering = ["country"]


class HolidayViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = HolidaySerializer
    queryset = Holiday.objects.all()
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description", "country"]
    ordering = ["date", "name"]

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), IsStaffOrAdminGroup()]
        return super().get_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()
        country = self.request.query_params.get("country")
        if country:
            queryset = queryset.filter(country=country)
        return queryset


class LettersViewSet(ApiErrorHandlingMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=SuratPermohonanRequestSerializer,
        responses={200: OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=["post"], url_path="surat-permohonan")
    def generate_surat_permohonan(self, request):
        serializer = SuratPermohonanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        customer_id = payload.get("customer_id")
        try:
            customer = Customer.objects.get(pk=customer_id)
        except Customer.DoesNotExist:
            return self.error_response("Customer not found", status.HTTP_404_NOT_FOUND)

        extra_data = {
            "doc_date": payload.get("doc_date") or "",
            "visa_type": payload.get("visa_type") or "",
            "name": payload.get("name") or "",
            "gender": payload.get("gender") or "",
            "country": payload.get("country") or "",
            "birth_place": payload.get("birth_place") or "",
            "birthdate": payload.get("birthdate") or "",
            "passport_no": payload.get("passport_no") or "",
            "passport_exp_date": payload.get("passport_exp_date") or "",
            "address_bali": payload.get("address_bali") or "",
        }

        service = LetterService(customer)

        try:
            data = service.generate_letter_data(extra_data)
            buffer = service.generate_letter_document(data)
            safe_name = slugify(f"surat_permohonan_{customer.full_name}", allow_unicode=False).replace("-", "_")
            safe_name = (safe_name or "surat_permohonan").replace(".", "_")
            filename = f"{safe_name}.docx"

            return FileResponse(
                buffer,
                as_attachment=True,
                filename=filename,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        except FileNotFoundError as exc:
            return self.error_response(str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:  # pragma: no cover - handled generically
            return self.error_response(
                f"Unable to generate Surat Permohonan: {exc}", status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        finally:
            service.cleanup_temp_files()

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="customer_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
            )
        ],
        responses=SuratPermohonanCustomerDataSerializer,
    )
    @action(detail=False, methods=["get"], url_path="customer-data/(?P<customer_id>[^/.]+)")
    def get_customer_data(self, request, customer_id=None):
        customer = get_object_or_404(Customer, pk=customer_id)
        nationality_code = customer.nationality.alpha3_code if customer.nationality else None

        response_data = {
            "name": customer.full_name,
            "gender": customer.gender or customer.get_gender_display(),
            "country": nationality_code,
            "birth_place": customer.birth_place or "",
            "birthdate": customer.birthdate.isoformat() if customer.birthdate else None,
            "passport_no": customer.passport_number or "",
            "passport_exp_date": (
                customer.passport_expiration_date.isoformat() if customer.passport_expiration_date else None
            ),
            "address_bali": customer.address_bali or "",
        }

        response_serializer = SuratPermohonanCustomerDataSerializer(response_data)
        return Response(response_serializer.data)


class DocumentTypeViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = DocumentType.objects.all()
    serializer_class = DocumentTypeSerializer
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description"]
    ordering = ["name"]

    def get_queryset(self):
        queryset = super().get_queryset()
        deprecated_param = self.request.query_params.get("deprecated")
        hide_deprecated = parse_bool(self.request.query_params.get("hide_deprecated"), True)

        if deprecated_param is not None:
            queryset = queryset.filter(deprecated=parse_bool(deprecated_param, False))
        elif hide_deprecated:
            queryset = queryset.filter(deprecated=False)

        return queryset

    def get_permissions(self):
        """Only staff or admin-group members can create/update/delete document types."""
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), IsStaffOrAdminGroup()]
        return super().get_permissions()

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="hide_deprecated",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="When true (default), hide deprecated document types.",
            ),
            OpenApiParameter(
                name="deprecated",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by explicit deprecated status.",
            ),
            OpenApiParameter(
                name="uses_customer_app_workflow",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter products by workflow-enabled flag.",
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Check if a document type can be deleted", responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["get"], url_path="can-delete")
    def can_delete(self, request, pk=None):
        """Check if document type can be safely deleted."""
        document_type = self.get_object()

        products = document_type.get_related_products()
        for product in products:
            if not product.deprecated:
                return Response(
                    {
                        "canDelete": False,
                        "message": f"Cannot delete '{document_type.name}' because it is used in one or more products.",
                        "warning": None,
                    }
                )

        return Response({"canDelete": True, "message": None, "warning": None})

    @action(detail=True, methods=["get"], url_path="deprecation-impact")
    def deprecation_impact(self, request, pk=None):
        document_type = self.get_object()
        related_products = [product for product in document_type.get_related_products() if not product.deprecated]
        return Response(
            {
                "documentTypeId": document_type.id,
                "documentTypeName": document_type.name,
                "relatedProducts": [
                    {
                        "id": product.id,
                        "name": product.name,
                        "code": product.code,
                    }
                    for product in related_products
                ],
                "count": len(related_products),
            }
        )

    def _perform_update_with_deprecation_rules(self, request, partial: bool):
        document_type = self.get_object()
        serializer = self.get_serializer(document_type, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        target_deprecated = serializer.validated_data.get("deprecated", document_type.deprecated)
        should_deprecate_now = not document_type.deprecated and bool(target_deprecated)
        related_products = []
        if should_deprecate_now:
            related_products = [product for product in document_type.get_related_products() if not product.deprecated]
            if related_products:
                confirm_related_deprecation = parse_bool(
                    request.data.get("deprecate_related_products")
                    or request.query_params.get("deprecate_related_products"),
                    False,
                )
                if not confirm_related_deprecation:
                    return Response(
                        {
                            "code": "deprecated_products_confirmation_required",
                            "message": "Deprecating this document type will also deprecate related products.",
                            "relatedProducts": [
                                {
                                    "id": product.id,
                                    "name": product.name,
                                    "code": product.code,
                                }
                                for product in related_products
                            ],
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

        self.perform_update(serializer)

        if should_deprecate_now and related_products:
            Product.objects.filter(id__in=[product.id for product in related_products]).update(
                deprecated=True,
                updated_by=request.user,
                updated_at=timezone.now(),
            )

        if getattr(document_type, "_prefetched_objects_cache", None):
            document_type._prefetched_objects_cache = {}

        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        return self._perform_update_with_deprecation_rules(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._perform_update_with_deprecation_rules(request, partial=True)


class CustomerViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Customer.objects.select_related("nationality").all()

        # Only apply search and active filters for the list action
        if self.action == "list":
            query = self.request.query_params.get("q") or self.request.query_params.get("search")
            if query:
                queryset = Customer.objects.search_customers(query).select_related("nationality")

            status_param = self.request.query_params.get("status")
            if status_param:
                if status_param == "active":
                    queryset = queryset.filter(active=True)
                elif status_param == "disabled":
                    queryset = queryset.filter(active=False)
            else:
                hide_disabled = self.request.query_params.get("hide_disabled", "true").lower() == "true"
                if hide_disabled:
                    queryset = queryset.filter(active=True)

        return queryset

    serializer_class = CustomerSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["first_name", "last_name", "email", "company_name", "passport_number"]
    ordering_fields = ["first_name", "last_name", "email", "company_name", "passport_number", "created_at"]
    ordering = ["-created_at"]

    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        query = request.query_params.get("q", "")
        customers = self.get_queryset().filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
        )
        page = self.paginate_queryset(customers)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(customers, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return self.error_response("Customer not found", status.HTTP_404_NOT_FOUND)

        customer.active = not customer.active
        customer.save(update_fields=["active"])
        return Response({"id": customer.id, "active": customer.active})

    @extend_schema(responses=CustomerUninvoicedApplicationSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="uninvoiced-applications")
    def uninvoiced_applications(self, request, pk=None):
        customer = self.get_object()
        applications = (
            customer.doc_applications.filter(invoice_applications__isnull=True, product__uses_customer_app_workflow=True)
            .select_related("customer", "product")
            .prefetch_related("invoice_applications__invoice")
            .distinct()
            .order_by("-id")
        )
        serializer = CustomerUninvoicedApplicationSerializer(applications, many=True)
        return Response(serializer.data)

    @extend_schema(responses=CustomerApplicationHistorySerializer(many=True))
    @action(detail=True, methods=["get"], url_path="applications-history")
    def applications_history(self, request, pk=None):
        customer = self.get_object()
        applications = (
            customer.doc_applications.filter(product__uses_customer_app_workflow=True).select_related("customer", "product")
            .prefetch_related(
                Prefetch(
                    "invoice_applications",
                    queryset=InvoiceApplication.objects.select_related("invoice"),
                )
            )
            .order_by("-id")
            .distinct()
        )
        serializer = CustomerApplicationHistorySerializer(applications, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        if not is_superuser(request.user):
            return self.error_response("You do not have permission to perform this action.", status.HTTP_403_FORBIDDEN)

        from core.services.bulk_delete import bulk_delete_customers

        query = (
            request.data.get("search_query") or request.data.get("searchQuery") or request.data.get("query") or ""
        ).strip()
        hide_disabled = parse_bool(request.data.get("hide_disabled") or request.data.get("hideDisabled"), True)

        count = bulk_delete_customers(query=query or None, hide_disabled=hide_disabled)
        return Response({"deleted_count": count})

    @extend_schema(
        request=PassportCheckSerializer,
        responses={202: OpenApiResponse(description="Job ID for SSE tracking")},
        operation_id="customers_check_passport_create",
    )
    @action(detail=False, methods=["post"], url_path="check-passport", parser_classes=[MultiPartParser, FormParser])
    def check_passport(self, request):
        """
        Check passport uploadability asynchronously.
        Returns an AsyncJob ID to track progress via SSE.
        """
        serializer = PassportCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # validated_data is a dict with guaranteed keys after is_valid()
        # use .get() to keep mypy/analysis happy
        file_obj = serializer.validated_data.get("file")  # type: ignore[assignment]
        method = serializer.validated_data.get("method")  # type: ignore[assignment]

        # Save file temporarily
        ext = file_obj.name.split(".")[-1] if "." in file_obj.name else "jpg"
        temp_path = f"tmp/passport_checks/{uuid.uuid4().hex}.{ext}"
        saved_path = default_storage.save(temp_path, file_obj)

        # Create AsyncJob
        job = AsyncJob.objects.create(
            task_name="check_passport_uploadability", status=AsyncJob.STATUS_PENDING, created_by=request.user
        )

        # Enqueue task
        check_passport_uploadability_task(str(job.id), saved_path, method)

        return Response({"job_id": str(job.id)}, status=status.HTTP_202_ACCEPTED)


class ProductViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    throttle_scope = None
    queryset = Product.objects.prefetch_related("tasks").all()
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "code", "description", "product_type"]
    ordering_fields = ["name", "code", "product_type", "base_price", "retail_price", "created_at", "updated_at"]
    ordering = ["name"]
    authenticated_lookup_actions = frozenset(
        {
            "list",
            "get_product_by_id",
            "get_products_by_product_type",
            "export_start",
            "import_start",
        }
    )

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return ProductCreateUpdateSerializer
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductSerializer

    def get_permissions(self):
        if self.action in self.authenticated_lookup_actions:
            self.permission_classes = [IsAuthenticated]
        else:
            self.permission_classes = [IsAuthenticated, IsAdminOrManagerGroup]
        return super().get_permissions()

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="hide_deprecated",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="When true (default), hide deprecated products.",
            ),
            OpenApiParameter(
                name="deprecated",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by explicit deprecated status.",
            ),
            OpenApiParameter(
                name="uses_customer_app_workflow",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter products by whether they use customer-application workflows.",
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        product_type = self.request.query_params.get("product_type")
        if product_type:
            queryset = queryset.filter(product_type=product_type)

        deprecated_param = self.request.query_params.get("deprecated")
        hide_deprecated = parse_bool(self.request.query_params.get("hide_deprecated"), True)
        if deprecated_param is not None:
            queryset = queryset.filter(deprecated=parse_bool(deprecated_param, False))
        elif hide_deprecated:
            queryset = queryset.filter(deprecated=False)

        workflow_param = self.request.query_params.get("uses_customer_app_workflow")
        if workflow_param is not None:
            queryset = queryset.filter(uses_customer_app_workflow=parse_bool(workflow_param, False))

        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["get"], url_path="can-delete")
    def can_delete(self, request, pk=None):
        product = self.get_object()
        from products.services import build_product_delete_preview

        preview = build_product_delete_preview(product, limit=1)
        return Response(
            {
                "can_delete": preview["can_delete"],
                "message": preview["message"],
                "requires_force_delete": preview["requires_force_delete"],
                "related_counts": preview["related_counts"],
            }
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"], url_path="delete-preview")
    def delete_preview(self, request, pk=None):
        if not is_superuser(request.user):
            return self.error_response("Only superusers can delete products.", status.HTTP_403_FORBIDDEN)

        from products.services import build_product_delete_preview

        product = self.get_object()
        preview = build_product_delete_preview(product)
        return Response(preview)

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="force-delete")
    def force_delete(self, request, pk=None):
        if not is_superuser(request.user):
            return self.error_response("Only superusers can delete products.", status.HTTP_403_FORBIDDEN)

        force_confirmed = parse_bool(
            request.data.get("force_delete_confirmed")
            or request.data.get("forceDeleteConfirmed")
            or request.data.get("confirmed")
        )
        if not force_confirmed:
            return self.error_response("Please confirm the force delete action.", status.HTTP_400_BAD_REQUEST)

        from products.services import force_delete_product

        product = self.get_object()
        result = force_delete_product(product)
        return Response({"deleted": True, **result})

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        if not is_superuser(request.user):
            return self.error_response("You do not have permission to perform this action.", status.HTTP_403_FORBIDDEN)

        from core.services.bulk_delete import bulk_delete_products

        query = (
            request.data.get("search_query") or request.data.get("searchQuery") or request.data.get("query") or ""
        ).strip()

        count = bulk_delete_products(query=query or None)
        return Response({"deleted_count": count})

    @action(detail=False, methods=["get"], url_path="get_product_by_id/(?P<product_id>[^/.]+)")
    def get_product_by_id(self, request, product_id=None):
        if not product_id:
            return self.error_response("Invalid request", status.HTTP_400_BAD_REQUEST)
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return self.error_response("Product does not exist", status.HTTP_404_NOT_FOUND)

        required_document_types = ordered_document_types(product.required_documents)
        optional_document_types = ordered_document_types(product.optional_documents)

        serialized_product = ProductSerializer(product, many=False)
        serialzed_document_types = DocumentTypeSerializer(required_document_types, many=True)
        serialzed_optional_document_types = DocumentTypeSerializer(optional_document_types, many=True)
        ordered_tasks = product.tasks.all().order_by("step")
        calendar_task = ordered_tasks.filter(add_task_to_calendar=True).first() or ordered_tasks.first()
        serialized_calendar_task = None
        if calendar_task:
            serialized_calendar_task = {
                "id": calendar_task.id,
                "name": calendar_task.name,
                "step": calendar_task.step,
                "duration": calendar_task.duration,
                "duration_is_business_days": calendar_task.duration_is_business_days,
                "add_task_to_calendar": calendar_task.add_task_to_calendar,
            }

        return Response(
            {
                "product": serialized_product.data,
                "required_documents": serialzed_document_types.data,
                "optional_documents": serialzed_optional_document_types.data,
                "calendar_task": serialized_calendar_task,
            }
        )

    @action(detail=False, methods=["get"], url_path="get_products_by_product_type/(?P<product_type>[^/.]+)")
    def get_products_by_product_type(self, request, product_type=None):
        products = Product.objects.filter(product_type=product_type, deprecated=False)
        page = self.paginate_queryset(products)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["post"],
        url_path="export/start",
        throttle_scope="products_export_start",
        throttle_classes=[AnonRateThrottle, UserRateThrottle, ScopedRateThrottle],
    )
    def export_start(self, request):
        from products.tasks import run_product_export_job

        namespace = "products_export_excel"
        query = (
            request.data.get("search_query") or request.data.get("searchQuery") or request.data.get("query") or ""
        ).strip()

        guard = prepare_async_enqueue(
            namespace=namespace,
            user=request.user,
            inflight_queryset=AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
            inflight_statuses=ASYNC_JOB_INFLIGHT_STATUSES,
            busy_message="Product export trigger is already being processed. Please retry in a moment.",
            deduplicated_response_builder=lambda existing_job: Response(
                {
                    "job_id": str(existing_job.id),
                    "status": existing_job.status,
                    "progress": existing_job.progress,
                    "queued": False,
                    "deduplicated": True,
                },
                status=status.HTTP_202_ACCEPTED,
            ),
            error_response_builder=self.error_response,
        )
        if guard.response is not None:
            return guard.response

        lock_key = guard.lock_key
        lock_token = guard.lock_token
        try:
            job = AsyncJob.objects.create(
                task_name=namespace,
                status=AsyncJob.STATUS_PENDING,
                progress=0,
                message="Queued product export...",
                created_by=request.user,
            )

            run_product_export_job(str(job.id), request.user.id if request.user else None, query)
        finally:
            if lock_key and lock_token:
                release_enqueue_guard(lock_key, lock_token)

        return Response(
            {
                "job_id": str(job.id),
                "status": job.status,
                "progress": job.progress,
                "queued": True,
                "deduplicated": False,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(
        parameters=[
            OpenApiParameter("job_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True),
        ],
    )
    @action(detail=False, methods=["get"], url_path=r"export/download/(?P<job_id>[^/.]+)")
    def export_download(self, request, job_id=None):
        try:
            job = AsyncJob.objects.get(id=job_id, created_by=request.user)
        except AsyncJob.DoesNotExist:
            return self.error_response("Job not found", status.HTTP_404_NOT_FOUND)

        if job.status != AsyncJob.STATUS_COMPLETED:
            return self.error_response("Job not completed yet", status.HTTP_400_BAD_REQUEST)

        result = job.result or {}
        file_path = result.get("file_path")
        filename = result.get("filename") or "products_export.xlsx"
        if not file_path:
            return self.error_response("Export file not available", status.HTTP_400_BAD_REQUEST)
        if not default_storage.exists(file_path):
            return self.error_response("Export file not found", status.HTTP_404_NOT_FOUND)

        response = FileResponse(
            default_storage.open(file_path, "rb"),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @action(
        detail=False,
        methods=["post"],
        url_path="import/start",
        parser_classes=[MultiPartParser, FormParser],
        throttle_scope="products_import_start",
        throttle_classes=[AnonRateThrottle, UserRateThrottle, ScopedRateThrottle],
    )
    def import_start(self, request):
        from products.tasks import run_product_import_job

        namespace = "products_import_excel"
        uploaded = request.FILES.get("file")
        if not uploaded:
            return self.error_response("No file uploaded", status.HTTP_400_BAD_REQUEST)

        filename = uploaded.name or "products_import.xlsx"
        ext = os.path.splitext(filename.lower())[1]
        if ext != ".xlsx":
            return self.error_response("Only .xlsx files are supported", status.HTTP_400_BAD_REQUEST)

        guard = prepare_async_enqueue(
            namespace=namespace,
            user=request.user,
            inflight_queryset=AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
            inflight_statuses=ASYNC_JOB_INFLIGHT_STATUSES,
            busy_message="Product import trigger is already being processed. Please retry in a moment.",
            deduplicated_response_builder=lambda existing_job: Response(
                {
                    "job_id": str(existing_job.id),
                    "status": existing_job.status,
                    "progress": existing_job.progress,
                    "queued": False,
                    "deduplicated": True,
                },
                status=status.HTTP_202_ACCEPTED,
            ),
            error_response_builder=self.error_response,
        )
        if guard.response is not None:
            return guard.response

        lock_key = guard.lock_key
        lock_token = guard.lock_token
        try:
            job = AsyncJob.objects.create(
                task_name=namespace,
                status=AsyncJob.STATUS_PENDING,
                progress=0,
                message="Queued product import...",
                created_by=request.user,
            )

            safe_name = get_valid_filename(os.path.basename(filename))
            input_path = os.path.join("tmpfiles", "product_imports", str(job.id), safe_name)
            saved_path = default_storage.save(input_path, uploaded)

            run_product_import_job(str(job.id), request.user.id if request.user else None, saved_path)
        finally:
            if lock_key and lock_token:
                release_enqueue_guard(lock_key, lock_token)

        return Response(
            {
                "job_id": str(job.id),
                "status": job.status,
                "progress": job.progress,
                "queued": True,
                "deduplicated": False,
            },
            status=status.HTTP_202_ACCEPTED,
        )
