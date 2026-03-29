"""
FILE_ROLE: Handles authentication, profile, and catalog API endpoints for the API app.

KEY_COMPONENTS:
- _set_refresh_cookie: Sets the JWT refresh and session-hint cookies.
- _clear_refresh_cookie: Clears the JWT auth cookies on logout.
- TokenAuthView: Issues access/refresh tokens and persists refresh state in cookies.
- TokenRefreshView: Refreshes access tokens and rotates the refresh cookies.
- UserProfileViewSet: Exposes current-user profile actions such as me, logout, avatar upload, and password change.
- UserSettingsViewSet: Reads and updates per-user settings through /me.
- CountryCodeViewSet: Read-only country list for dropdown use.

INTERACTIONS:
- Depends on: api.utils.ai_model_pricing, api.utils.idempotency, api.utils.stream_payloads, .views_imports
- Consumed by: frontend auth bootstrap, profile screens, and dropdown/catalog consumers.

AI_GUIDELINES:
- Keep HTTP/auth-cookie handling thin and consistent with the JWT settings contract.
- Do not move business orchestration or persistence-heavy logic into these view classes when a service already owns it.
- Preserve the canonical refresh-cookie names, paths, domains, and session-hint behavior.
"""

from api.utils.ai_model_pricing import price_to_display
from api.utils.idempotency import (
    build_request_idempotency_fingerprint,
    resolve_request_idempotent_job,
    store_request_idempotent_job,
)
from api.utils.stream_payloads import build_async_job_links, build_async_job_start_payload
from rest_framework.renderers import JSONRenderer
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView

from .views_imports import *


def _refresh_cookie_name() -> str:
    return getattr(settings, "JWT_REFRESH_COOKIE_NAME", "bs_refresh_token")


def _refresh_session_hint_cookie_name() -> str:
    return getattr(settings, "JWT_REFRESH_SESSION_HINT_COOKIE_NAME", "bs_refresh_session_hint")


def _refresh_cookie_path() -> str:
    return getattr(settings, "JWT_REFRESH_COOKIE_PATH", "/api/token/refresh/")


def _refresh_session_hint_cookie_path() -> str:
    return getattr(settings, "JWT_REFRESH_SESSION_HINT_COOKIE_PATH", "/")


def _refresh_cookie_domain() -> str | None:
    return getattr(settings, "JWT_REFRESH_COOKIE_DOMAIN", None)


def _refresh_cookie_secure() -> bool:
    return bool(getattr(settings, "JWT_REFRESH_COOKIE_SECURE", False))


def _refresh_cookie_samesite() -> str:
    return getattr(settings, "JWT_REFRESH_COOKIE_SAMESITE", "Lax")


def _refresh_cookie_max_age_seconds() -> int | None:
    lifetime = getattr(settings, "SIMPLE_JWT", {}).get("REFRESH_TOKEN_LIFETIME")
    try:
        return int(lifetime.total_seconds()) if lifetime is not None else None
    except Exception:
        return None


def _set_refresh_cookie(response: Response, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    response.set_cookie(
        key=_refresh_cookie_name(),
        value=refresh_token,
        max_age=_refresh_cookie_max_age_seconds(),
        httponly=True,
        secure=_refresh_cookie_secure(),
        samesite=_refresh_cookie_samesite(),
        path=_refresh_cookie_path(),
        domain=_refresh_cookie_domain(),
    )
    response.set_cookie(
        key=_refresh_session_hint_cookie_name(),
        value="1",
        max_age=_refresh_cookie_max_age_seconds(),
        httponly=False,
        secure=_refresh_cookie_secure(),
        samesite=_refresh_cookie_samesite(),
        path=_refresh_session_hint_cookie_path(),
        domain=_refresh_cookie_domain(),
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        _refresh_cookie_name(),
        path=_refresh_cookie_path(),
        domain=_refresh_cookie_domain(),
    )
    response.delete_cookie(
        _refresh_session_hint_cookie_name(),
        path=_refresh_session_hint_cookie_path(),
        domain=_refresh_cookie_domain(),
    )


class TokenAuthView(TokenObtainPairView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainSerializer
    renderer_classes = [JSONRenderer]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        refresh_token = payload.pop("refresh_token", None)
        response = Response(build_success_payload(payload, request=request), status=status.HTTP_200_OK)
        _set_refresh_cookie(response, refresh_token if isinstance(refresh_token, str) else None)
        return response


class TokenRefreshView(SimpleJWTTokenRefreshView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = CustomTokenRefreshSerializer
    renderer_classes = [JSONRenderer]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        refresh_token = payload.pop("refresh_token", None)
        response = Response(build_success_payload(payload, request=request), status=status.HTTP_200_OK)
        _set_refresh_cookie(response, refresh_token if isinstance(refresh_token, str) else None)
        return response


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

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def logout(self, request):
        """Logout current user and record it in Django."""
        django_logout(request)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response

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


class AiModelViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStaffOrAdminGroup]
    queryset = AiModel.objects.all()
    serializer_class = AiModelSerializer
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["provider", "model_id", "name", "description", "modality"]
    ordering_fields = ["provider", "name", "model_id", "updated_at", "created_at"]
    ordering = ["provider", "name"]

    @action(detail=False, methods=["get"], url_path="catalog")
    def catalog(self, request):
        return Response(build_success_payload(AIRuntimeSettingsService.get_model_catalog(), request=request))

    @extend_schema(
        parameters=[
            OpenApiParameter(name="q", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="limit", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY, required=False),
        ]
    )
    @action(detail=False, methods=["get"], url_path="openrouter-search")
    def openrouter_search(self, request):
        query = str(request.query_params.get("q") or "").strip().lower()
        raw_limit = request.query_params.get("limit")
        try:
            limit = min(max(int(raw_limit or 20), 1), 50)
        except (TypeError, ValueError):
            return self.error_response("Invalid limit parameter.", status.HTTP_400_BAD_REQUEST)
        api_key = getattr(settings, "OPENROUTER_API_KEY", None)
        base_url = str(
            AIRuntimeSettingsService.get("OPENROUTER_API_BASE_URL") or "https://openrouter.ai/api/v1"
        ).rstrip("/")

        if not api_key:
            return Response(
                build_success_payload(
                    {"results": [], "message": "OPENROUTER_API_KEY is not configured."},
                    request=request,
                ),
                status=200,
            )

        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        try:
            response = requests.get(f"{base_url}/models", headers=headers, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return self.error_response(f"OpenRouter model lookup failed: {exc}", status.HTTP_502_BAD_GATEWAY)

        raw_models = payload.get("data", []) if isinstance(payload, dict) else []
        results = []
        for item in raw_models:
            model_id = str(item.get("id") or "").strip()
            name = str(item.get("name") or model_id).strip()
            description = str(item.get("description") or "").strip()
            searchable = f"{model_id} {name} {description}".lower()
            if query and query not in searchable:
                continue

            # Extract architecture info
            architecture = item.get("architecture") if isinstance(item.get("architecture"), dict) else {}
            modality = str(architecture.get("modality") or "").strip()
            tokenizer = str(architecture.get("tokenizer") or "").strip()
            instruct_type = str(architecture.get("instruct_type") or "").strip()

            # Extract pricing info - OpenRouter uses these field names
            pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
            prompt_price = pricing.get("prompt")
            completion_price = pricing.get("completion")
            image_price = pricing.get("image")
            request_price = pricing.get("request")

            # Extract top provider info
            top_provider = item.get("top_provider") if isinstance(item.get("top_provider"), dict) else {}
            # OpenRouter doesn't return id/name in top_provider, use model_id prefix as provider
            provider_prefix = model_id.split("/")[0] if "/" in model_id else model_id
            top_provider_id = provider_prefix
            provider_name = provider_prefix.title()

            # Extract other fields
            context_length = item.get("context_length")
            max_completion_tokens = top_provider.get("max_completion_tokens")
            supported_parameters = item.get("supported_parameters", [])
            per_request_limits = item.get("per_request_limits", {})

            # Detect capabilities from searchable text and modality
            vision = "image" in modality.lower() or "vision" in searchable or "multimodal" in searchable
            file_upload = "file" in searchable or "document" in searchable
            reasoning = "reason" in searchable or "think" in searchable or "reasoning" in searchable

            results.append(
                {
                    "provider": "openrouter",
                    "model_id": model_id,
                    "name": name,
                    "description": description,
                    "vision": vision,
                    "file_upload": file_upload,
                    "reasoning": reasoning,
                    "context_length": context_length,
                    "max_completion_tokens": max_completion_tokens,
                    "modality": modality,
                    "architecture_modality": modality,
                    "architecture_tokenizer": tokenizer,
                    "instruct_type": instruct_type,
                    "prompt_price_per_token": prompt_price,
                    "completion_price_per_token": completion_price,
                    "image_price": image_price,
                    "request_price": request_price,
                    "pricing_display": {
                        "prompt_price_per_million_tokens": price_to_display(prompt_price),
                        "completion_price_per_million_tokens": price_to_display(completion_price),
                        "image_price_per_million_tokens": price_to_display(image_price),
                        "request_price_per_million_tokens": price_to_display(request_price),
                    },
                    "top_provider_id": top_provider_id,
                    "provider_name": provider_name,
                    "supported_parameters": supported_parameters,
                    "per_request_limits": per_request_limits,
                    "source": "openrouter",
                    "raw_metadata": item,
                }
            )
            if len(results) >= limit:
                break

        return Response(build_success_payload({"results": results}, request=request))


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
        default_hide = self.action not in [
            "retrieve",
            "update",
            "partial_update",
            "destroy",
            "can_delete",
            "deprecation_impact",
        ]
        hide_deprecated = parse_bool(self.request.query_params.get("hide_deprecated"), default_hide)

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
                    build_success_payload(
                        {
                            "canDelete": False,
                            "message": f"Cannot delete '{document_type.name}' because it is used in one or more products.",
                            "warning": None,
                        },
                        request=request,
                    )
                )

        return Response(build_success_payload({"canDelete": True, "message": None, "warning": None}, request=request))

    @action(detail=True, methods=["get"], url_path="deprecation-impact")
    def deprecation_impact(self, request, pk=None):
        document_type = self.get_object()
        related_products = [product for product in document_type.get_related_products() if not product.deprecated]
        return Response(
            build_success_payload(
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
                },
                request=request,
            )
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
                        build_error_payload(
                            code="deprecated_products_confirmation_required",
                            message="Deprecating this document type will also deprecate related products.",
                            details={
                                "relatedProducts": [
                                    {
                                        "id": product.id,
                                        "name": product.name,
                                        "code": product.code,
                                    }
                                    for product in related_products
                                ]
                            },
                            request=request,
                        ),
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
    throttle_cache_fail_open_actions = {"check_passport": False}

    @staticmethod
    def _with_case_insensitive_name_sorting(queryset):
        return queryset.annotate(
            sort_last_name=Coalesce(
                NullIf(Lower("last_name"), Value("")),
                NullIf(Lower("company_name"), Value("")),
                NullIf(Lower("first_name"), Value("")),
                Value(""),
            ),
            sort_first_name=Coalesce(
                NullIf(Lower("first_name"), Value("")),
                NullIf(Lower("company_name"), Value("")),
                Value(""),
            ),
            sort_company_name=Coalesce(
                NullIf(Lower("company_name"), Value("")),
                Value(""),
            ),
        )

    def get_queryset(self):
        queryset = self._with_case_insensitive_name_sorting(Customer.objects.select_related("nationality").all())

        # Keep list and explicit search action behavior aligned.
        if self.action in {"list", "search"}:
            query = self.request.query_params.get("q") or self.request.query_params.get("search")
            if query:
                queryset = self._with_case_insensitive_name_sorting(
                    Customer.objects.search_customers(query).select_related("nationality")
                )

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
    ordering_fields = [
        "first_name",
        "last_name",
        "email",
        "company_name",
        "passport_number",
        "created_at",
        "sort_last_name",
        "sort_first_name",
        "sort_company_name",
    ]
    ordering = ["-created_at"]

    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        customers = self.get_queryset()
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
        return Response(build_success_payload({"id": customer.id, "active": customer.active}, request=request))

    @extend_schema(responses=CustomerUninvoicedApplicationSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="uninvoiced-applications")
    def uninvoiced_applications(self, request, pk=None):
        customer = self.get_object()
        applications = (
            customer.doc_applications.filter(
                invoice_applications__isnull=True, product__uses_customer_app_workflow=True
            )
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
            customer.doc_applications.filter(product__uses_customer_app_workflow=True)
            .select_related(
                "customer",
                "customer__nationality",
                "product",
                "product__product_category",
                "product__created_by",
                "product__updated_by",
            )
            .prefetch_related(
                Prefetch(
                    "documents",
                    queryset=Document.objects.select_related("doc_type"),
                ),
                Prefetch(
                    "invoice_applications",
                    queryset=InvoiceApplication.objects.select_related("invoice"),
                ),
            )
            .order_by("-id")
            .distinct()
        )
        page = self.paginate_queryset(applications)
        if page is not None:
            serializer = CustomerApplicationHistorySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = CustomerApplicationHistorySerializer(applications, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=inline_serializer(
            name="CustomersBulkDeleteRequest",
            fields={
                "searchQuery": serializers.CharField(required=False, allow_blank=True),
                "hideDisabled": serializers.BooleanField(required=False),
            },
        ),
        responses={
            200: inline_serializer(
                name="CustomersBulkDeleteResponse",
                fields={"deletedCount": serializers.IntegerField()},
            )
        },
    )
    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        if not is_superuser_or_admin_group(request.user):
            return self.error_response("You do not have permission to perform this action.", status.HTTP_403_FORBIDDEN)

        from core.services.bulk_delete import bulk_delete_customers

        query = (
            request.data.get("search_query") or request.data.get("searchQuery") or request.data.get("query") or ""
        ).strip()
        hide_disabled = parse_bool(request.data.get("hide_disabled") or request.data.get("hideDisabled"), True)

        count = bulk_delete_customers(query=query or None, hide_disabled=hide_disabled)
        return Response(build_success_payload({"deletedCount": count}, request=request))

    @extend_schema(
        request=PassportCheckSerializer,
        responses={202: OpenApiResponse(description="Job ID for SSE tracking")},
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
        request_fingerprint = build_request_idempotency_fingerprint(request)

        idempotency_cache_key, cached_job = resolve_request_idempotent_job(
            request=request,
            namespace="check_passport_uploadability",
            user_id=request.user.id,
            queryset=AsyncJob.objects.filter(task_name="check_passport_uploadability", created_by=request.user),
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
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        # Save file temporarily
        ext = file_obj.name.split(".")[-1] if "." in file_obj.name else "jpg"
        temp_path = f"tmp/passport_checks/{uuid.uuid4().hex}.{ext}"
        saved_path = default_storage.save(temp_path, file_obj)

        # Create AsyncJob
        job = AsyncJob.objects.create(
            task_name="check_passport_uploadability", status=AsyncJob.STATUS_PENDING, created_by=request.user
        )

        # Enqueue task
        check_passport_uploadability_task.delay(str(job.id), saved_path, method)
        store_request_idempotent_job(cache_key=idempotency_cache_key, job_id=job.id, fingerprint=request_fingerprint)

        return Response(
            build_async_job_start_payload(
                job_id=job.id,
                status=AsyncJob.STATUS_PENDING,
                progress=0,
                queued=True,
                deduplicated=False,
            ),
            status=status.HTTP_202_ACCEPTED,
        )


class ProductOrderingFilter(filters.OrderingFilter):
    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        if not ordering:
            return ordering
        mapped = []
        for field in ordering:
            prefix = "-" if field.startswith("-") else ""
            name = field[1:] if prefix else field
            if name == "product_type":
                mapped.append(f"{prefix}product_category__product_type")
            else:
                mapped.append(field)
        return mapped


class ProductViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    throttle_scope = None
    throttle_cache_fail_open_actions = {
        "export_start": False,
        "price_list_print_start": False,
        "import_start": False,
    }
    queryset = Product.objects.select_related("product_category").prefetch_related("tasks").all()
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, ProductOrderingFilter]
    search_fields = ["name", "code", "description", "product_category__product_type"]
    ordering_fields = [
        "name",
        "code",
        "product_type",
        "product_category__product_type",
        "product_category__name",
        "base_price",
        "retail_price",
        "created_at",
        "updated_at",
    ]
    ordering = ["name"]
    authenticated_lookup_actions = frozenset(
        {
            "category_options",
            "list",
            "get_product_by_id",
            "get_products_by_product_type",
            "export_start",
            "price_list_print_download",
            "price_list_print_start",
            "import_start",
        }
    )

    def get_throttles(self):
        action_scopes = {
            "export_start": "products_export_start",
            "price_list_print_start": "products_price_list_print_start",
            "import_start": "products_import_start",
        }
        self.throttle_scope = action_scopes.get(getattr(self, "action", None))
        return super().get_throttles()

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return ProductCreateUpdateSerializer
        if self.action == "category_options":
            return ProductCategoryFilterOptionSerializer
        if self.action == "import_start":
            return ProductImportStartSerializer
        if self.action == "price_list_print_start":
            return ProductPriceListPrintStartSerializer
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductSerializer

    def get_permissions(self):
        # We now rely on dynamic RBAC evaluation by the frontend, so the underlying API
        # just requires authentication to ensure basic safety. The dynamic rules
        # determine actual data exposure and visibility.
        self.permission_classes = [IsAuthenticated]
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
                name="product_category",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by product category name (comma-separated).",
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

    def _get_filtered_product_queryset(self, *, include_category_filter: bool = True):
        queryset = super().get_queryset()
        product_type = self.request.query_params.get("product_type")
        if product_type:
            queryset = queryset.filter(product_category__product_type=product_type)

        if include_category_filter:
            product_category_param = self.request.query_params.get("product_category")
            if product_category_param:
                categories = [item.strip() for item in product_category_param.split(",") if item.strip()]
                if categories:
                    queryset = queryset.filter(product_category__name__in=categories)

        deprecated_param = self.request.query_params.get("deprecated")
        default_hide = self.action not in ["retrieve", "update", "partial_update", "destroy"]
        hide_deprecated = parse_bool(self.request.query_params.get("hide_deprecated"), default_hide)

        if deprecated_param is not None:
            queryset = queryset.filter(deprecated=parse_bool(deprecated_param, False))
        elif hide_deprecated:
            queryset = queryset.filter(deprecated=False)

        workflow_param = self.request.query_params.get("uses_customer_app_workflow")
        if workflow_param is not None:
            queryset = queryset.filter(uses_customer_app_workflow=parse_bool(workflow_param, False))

        return queryset

    def get_queryset(self):
        return self._get_filtered_product_queryset()

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="hide_deprecated",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="When true (default), hide categories that only belong to deprecated products.",
            ),
            OpenApiParameter(
                name="deprecated",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter category options by explicit deprecated product status.",
            ),
            OpenApiParameter(
                name="product_type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Restrict category options to a product type.",
            ),
            OpenApiParameter(
                name="uses_customer_app_workflow",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Restrict category options to workflow-enabled products.",
            ),
        ],
        responses=ProductCategoryFilterOptionSerializer(many=True),
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="category-options",
        pagination_class=None,
        filter_backends=[],
    )
    def category_options(self, request):
        categories = (
            ProductCategory.objects.filter(
                products__in=self._get_filtered_product_queryset(include_category_filter=False)
            )
            .distinct()
            .order_by("name")
        )
        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)

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
            build_success_payload(
                {
                    "canDelete": preview["canDelete"],
                    "message": preview["message"],
                    "requiresForceDelete": preview["requiresForceDelete"],
                    "relatedCounts": preview["relatedCounts"],
                },
                request=request,
            )
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"], url_path="delete-preview")
    def delete_preview(self, request, pk=None):
        if not is_superuser_or_admin_group(request.user):
            return self.error_response("Only superusers can delete products.", status.HTTP_403_FORBIDDEN)

        from products.services import build_product_delete_preview

        product = self.get_object()
        preview = build_product_delete_preview(product)
        return Response(build_success_payload(preview, request=request))

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="force-delete")
    def force_delete(self, request, pk=None):
        if not is_superuser_or_admin_group(request.user):
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
        return Response(build_success_payload({"deleted": True, **result}, request=request))

    @extend_schema(
        request=inline_serializer(
            name="ProductsBulkDeleteRequest",
            fields={
                "searchQuery": serializers.CharField(required=False, allow_blank=True),
            },
        ),
        responses={
            200: inline_serializer(
                name="ProductsBulkDeleteResponse",
                fields={"deletedCount": serializers.IntegerField()},
            )
        },
    )
    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        if not is_superuser_or_admin_group(request.user):
            return self.error_response("You do not have permission to perform this action.", status.HTTP_403_FORBIDDEN)

        from core.services.bulk_delete import bulk_delete_products

        query = (
            request.data.get("search_query") or request.data.get("searchQuery") or request.data.get("query") or ""
        ).strip()

        count = bulk_delete_products(query=query or None)
        return Response(build_success_payload({"deletedCount": count}, request=request))

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
                "durationIsBusinessDays": calendar_task.duration_is_business_days,
                "addTaskToCalendar": calendar_task.add_task_to_calendar,
            }

        return Response(
            {
                "product": serialized_product.data,
                "requiredDocuments": serialzed_document_types.data,
                "optionalDocuments": serialzed_optional_document_types.data,
                "calendarTask": serialized_calendar_task,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="product_type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                required=True,
                description="Product type (visa|other).",
            ),
        ]
    )
    @action(detail=False, methods=["get"], url_path="get_products_by_product_type/(?P<product_type>[^/.]+)")
    def get_products_by_product_type(self, request, product_type=None):
        products = Product.objects.select_related("product_category").filter(
            product_category__product_type=product_type,
            deprecated=False,
        )
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
        request_fingerprint = build_request_idempotency_fingerprint(request)
        query = (
            request.data.get("search_query") or request.data.get("searchQuery") or request.data.get("query") or ""
        ).strip()

        idempotency_cache_key, cached_job = resolve_request_idempotent_job(
            request=request,
            namespace=namespace,
            user_id=request.user.id,
            queryset=AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
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
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        guard = prepare_async_enqueue(
            namespace=namespace,
            user=request.user,
            inflight_queryset=AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
            inflight_statuses=ASYNC_JOB_INFLIGHT_STATUSES,
            busy_message="Product export trigger is already being processed. Please retry in a moment.",
            deduplicated_response_builder=lambda existing_job: Response(
                build_async_job_start_payload(
                    job_id=existing_job.id,
                    status=existing_job.status,
                    progress=existing_job.progress,
                    queued=False,
                    deduplicated=True,
                ),
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
                status=AsyncJob.STATUS_PENDING,
                progress=job.progress,
                queued=True,
                deduplicated=False,
            ),
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(
        request=None,
        responses={202: ProductPriceListPrintStartResponseSerializer},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="price-list/print/start",
        throttle_scope="products_price_list_print_start",
        throttle_classes=[AnonRateThrottle, UserRateThrottle, ScopedRateThrottle],
    )
    def price_list_print_start(self, request):
        from products.tasks import run_product_price_list_print_job

        namespace = "products_price_list_print"
        request_fingerprint = build_request_idempotency_fingerprint(request)

        idempotency_cache_key, cached_job = resolve_request_idempotent_job(
            request=request,
            namespace=namespace,
            user_id=request.user.id,
            queryset=AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
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
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        guard = prepare_async_enqueue(
            namespace=namespace,
            user=request.user,
            inflight_queryset=AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
            inflight_statuses=ASYNC_JOB_INFLIGHT_STATUSES,
            busy_message="Price list print preparation is already being processed. Please retry in a moment.",
            deduplicated_response_builder=lambda existing_job: Response(
                build_async_job_start_payload(
                    job_id=existing_job.id,
                    status=existing_job.status,
                    progress=existing_job.progress,
                    queued=False,
                    deduplicated=True,
                ),
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
                message="Queued printable price list generation...",
                created_by=request.user,
            )

            run_product_price_list_print_job(str(job.id), request.user.id if request.user else None)
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
                status=AsyncJob.STATUS_PENDING,
                progress=job.progress,
                queued=True,
                deduplicated=False,
            ),
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(
        parameters=[
            OpenApiParameter("job_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True),
        ],
        responses={200: OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=["get"], url_path=r"price-list/print/download/(?P<job_id>[^/.]+)")
    def price_list_print_download(self, request, job_id=None):
        try:
            job = AsyncJob.objects.get(id=job_id, created_by=request.user)
        except AsyncJob.DoesNotExist:
            return self.error_response("Job not found", status.HTTP_404_NOT_FOUND)

        if job.status != AsyncJob.STATUS_COMPLETED:
            return self.error_response("Job not completed yet", status.HTTP_400_BAD_REQUEST)

        result = job.result or {}
        file_path = result.get("file_path")
        filename = result.get("filename") or "public_price_list.pdf"
        if not file_path:
            return self.error_response("Printable price list file is not available", status.HTTP_400_BAD_REQUEST)
        if not default_storage.exists(file_path):
            return self.error_response("Printable price list file not found", status.HTTP_404_NOT_FOUND)

        response = FileResponse(default_storage.open(file_path, "rb"), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response

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

    @extend_schema(
        request=ProductImportStartSerializer,
        responses={202: ProductImportStartResponseSerializer},
    )
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
        request_fingerprint = build_request_idempotency_fingerprint(request)
        uploaded = request.FILES.get("file")
        if not uploaded:
            return self.error_response("No file uploaded", status.HTTP_400_BAD_REQUEST)

        filename = uploaded.name or "products_import.xlsx"
        ext = os.path.splitext(filename.lower())[1]
        if ext != ".xlsx":
            return self.error_response("Only .xlsx files are supported", status.HTTP_400_BAD_REQUEST)

        idempotency_cache_key, cached_job = resolve_request_idempotent_job(
            request=request,
            namespace=namespace,
            user_id=request.user.id,
            queryset=AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
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
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        guard = prepare_async_enqueue(
            namespace=namespace,
            user=request.user,
            inflight_queryset=AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
            inflight_statuses=ASYNC_JOB_INFLIGHT_STATUSES,
            busy_message="Product import trigger is already being processed. Please retry in a moment.",
            deduplicated_response_builder=lambda existing_job: Response(
                build_async_job_start_payload(
                    job_id=existing_job.id,
                    status=existing_job.status,
                    progress=existing_job.progress,
                    queued=False,
                    deduplicated=True,
                ),
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
                status=AsyncJob.STATUS_PENDING,
                progress=job.progress,
                queued=True,
                deduplicated=False,
            ),
            status=status.HTTP_202_ACCEPTED,
        )
