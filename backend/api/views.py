import json
import logging
import mimetypes
import os
import time
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from api.async_controls import (
    acquire_enqueue_guard,
    build_user_enqueue_guard_key,
    increment_guard_counter,
    release_enqueue_guard,
)
from api.permissions import (
    STAFF_OR_ADMIN_PERMISSION_REQUIRED_ERROR,
    IsAdminOrManagerGroup,
    IsStaffOrAdminGroup,
    is_staff_or_admin_group,
    is_superuser,
)
from api.serializers import (
    AdminPushNotificationSendSerializer,
    AdminWhatsappTestSendSerializer,
    AsyncJobSerializer,
    AvatarUploadSerializer,
    CalendarReminderBulkCreateSerializer,
    CalendarReminderCreateSerializer,
    CalendarReminderInboxMarkReadSerializer,
    CalendarReminderInboxSnoozeSerializer,
    CalendarReminderSerializer,
    ChangePasswordSerializer,
    CountryCodeSerializer,
    CustomerApplicationHistorySerializer,
    CustomerApplicationQuickCreateSerializer,
    CustomerQuickCreateSerializer,
    CustomerSerializer,
    CustomerUninvoicedApplicationSerializer,
    DashboardStatsSerializer,
    DocApplicationDetailSerializer,
    DocApplicationInvoiceSerializer,
    DocApplicationSerializerWithRelations,
    DocumentMergeSerializer,
    DocumentSerializer,
    DocumentTypeSerializer,
    DocWorkflowSerializer,
    HolidaySerializer,
    InvoiceCreateUpdateSerializer,
    InvoiceDetailSerializer,
    InvoiceListSerializer,
    PaymentSerializer,
    ProductCreateUpdateSerializer,
    ProductDetailSerializer,
    ProductQuickCreateSerializer,
    ProductSerializer,
    PushNotificationTestSerializer,
    SuratPermohonanCustomerDataSerializer,
    SuratPermohonanRequestSerializer,
    UserProfileSerializer,
    UserSettingsSerializer,
    WebPushSubscriptionDeleteSerializer,
    WebPushSubscriptionSerializer,
    WebPushSubscriptionUpsertSerializer,
    WorkflowNotificationSerializer,
    ordered_document_types,
)
from api.serializers.auth_serializer import CustomTokenObtainSerializer
from api.serializers.passport_check_serializer import PassportCheckSerializer
from api.utils.sse_auth import sse_token_auth_required
from business_suite.authentication import JwtOrMockAuthentication
from core.models import (
    AsyncJob,
    CalendarReminder,
    CountryCode,
    DocumentOCRJob,
    Holiday,
    OCRJob,
    UserProfile,
    UserSettings,
    WebPushSubscription,
)
from core.models.async_job import AsyncJob
from core.services.calendar_reminder_service import CalendarReminderService
from core.services.calendar_reminder_stream import (
    get_calendar_reminder_stream_cursor,
    get_calendar_reminder_stream_last_event,
)
from core.services.document_merger import DocumentMerger, DocumentMergerError
from core.services.ocr_preview_storage import get_ocr_preview_url
from core.services.push_notifications import FcmConfigurationError, PushNotificationService
from core.services.quick_create import create_quick_customer, create_quick_customer_application, create_quick_product
from core.tasks.cron_jobs import enqueue_clear_cache_now, enqueue_full_backup_now
from core.tasks.document_ocr import run_document_ocr_job
from core.tasks.document_validation import run_document_validation
from core.tasks.ocr import run_ocr_job
from core.utils.dateutils import calculate_due_date
from core.utils.pdf_converter import PDFConverter, PDFConverterError
from customer_applications.models import DocApplication, Document, DocWorkflow, WorkflowNotification
from customer_applications.services.workflow_notification_stream import (
    RECENT_WORKFLOW_NOTIFICATION_WINDOW_HOURS,
    get_workflow_notification_stream_cursor,
    get_workflow_notification_stream_last_event,
)
from customers.models import Customer
from customers.tasks import check_passport_uploadability_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import logout as django_logout
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import (
    Case,
    Count,
    DecimalField,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename, slugify
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from invoices.models import InvoiceDownloadJob
from invoices.models.invoice import Invoice, InvoiceApplication
from invoices.services.InvoiceService import InvoiceService
from invoices.tasks.download_jobs import run_invoice_download_job
from letters.services.LetterService import LetterService
from payments.models import Payment
from products.models import Product
from products.models.document_type import DocumentType
from products.models.task import Task
from rest_framework import filters, pagination, serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView

logger = logging.getLogger(__name__)


class OCRPlaceholderSerializer(serializers.Serializer):
    """Schema placeholder for OCR viewset endpoints."""


class DocumentOCRPlaceholderSerializer(serializers.Serializer):
    """Schema placeholder for Document OCR viewset endpoints."""


class ComputePlaceholderSerializer(serializers.Serializer):
    """Schema placeholder for Compute viewset endpoints."""


@csrf_exempt
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def whatsapp_webhook(request):
    """Meta WhatsApp webhook endpoint (verification + delivery statuses + incoming replies)."""
    from notifications.services.providers import process_whatsapp_webhook_payload, verify_meta_webhook_signature

    webhook_logger = logging.getLogger("notifications.whatsapp_webhook")

    if request.method == "GET":
        mode = request.query_params.get("hub.mode")
        challenge = request.query_params.get("hub.challenge", "")
        verify_token = request.query_params.get("hub.verify_token")

        # Meta webhook verification handshake
        if mode == "subscribe":
            expected_token = getattr(settings, "META_TOKEN_CLIENT", "")
            if verify_token and expected_token and verify_token == expected_token:
                return HttpResponse(challenge, status=status.HTTP_200_OK, content_type="text/plain")
            return Response({"error": "Invalid verify token"}, status=status.HTTP_403_FORBIDDEN)

        return Response({"status": "ok"}, status=status.HTTP_200_OK)

    signature_header = request.headers.get("X-Hub-Signature-256")
    signature_valid = verify_meta_webhook_signature(request.body, signature_header)
    enforce_signature = getattr(settings, "META_WEBHOOK_ENFORCE_SIGNATURE", True)
    if not signature_valid:
        if enforce_signature:
            webhook_logger.warning("Rejected WhatsApp webhook due to invalid signature.")
            return Response({"error": "Invalid webhook signature"}, status=status.HTTP_403_FORBIDDEN)
        webhook_logger.warning("Processing WhatsApp webhook with invalid signature (enforcement disabled).")

    data = request.data
    if not isinstance(data, dict):
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            data = request.POST.dict()

    result = process_whatsapp_webhook_payload(data)
    webhook_logger.info(
        "Processed WhatsApp webhook: signature_valid=%s status_updates=%s replies=%s",
        signature_valid,
        result.get("status_updates", 0),
        result.get("replies", 0),
    )
    return Response({"status": "received"}, status=status.HTTP_200_OK)


def parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}


def restrict_to_owner_unless_privileged(queryset, user, owner_field: str = "created_by"):
    if is_staff_or_admin_group(user):
        return queryset
    return queryset.filter(**{owner_field: user})


ASYNC_JOB_INFLIGHT_STATUSES = (AsyncJob.STATUS_PENDING, AsyncJob.STATUS_PROCESSING)
QUEUE_JOB_INFLIGHT_STATUSES = ("queued", "processing")


def _latest_inflight_job(queryset, statuses):
    return queryset.filter(status__in=statuses).order_by("-created_at", "-updated_at").first()


def _get_enqueue_guard_token(*, namespace: str, user, scope: str | None = None) -> tuple[str, str | None]:
    lock_key = build_user_enqueue_guard_key(
        namespace=namespace,
        user_id=getattr(user, "id", None),
        scope=scope,
    )
    return lock_key, acquire_enqueue_guard(lock_key)


def _observe_async_guard_event(
    *,
    namespace: str,
    event: str,
    user,
    job_id=None,
    status_code: int | None = None,
    detail: str | None = None,
    warning: bool = False,
) -> int:
    counter = increment_guard_counter(namespace=namespace, event=event)
    log_fn = logger.warning if warning else logger.info
    log_fn(
        "async_guard event=%s namespace=%s counter=%s user_id=%s job_id=%s status_code=%s detail=%s",
        event,
        namespace,
        counter,
        getattr(user, "id", None),
        job_id,
        status_code,
        detail or "",
    )
    return counter


class ApiErrorHandlingMixin:
    def error_response(self, message, status_code=status.HTTP_400_BAD_REQUEST, details=None):
        payload = {"error": message}
        if details is not None:
            payload["details"] = details
        return Response(payload, status=status_code)

    def handle_exception(self, exc):
        from django.db.models.deletion import ProtectedError

        if isinstance(exc, ProtectedError):
            message = exc.args[0] if getattr(exc, "args", None) else "Cannot delete because related objects exist."
            return self.error_response(str(message), status.HTTP_409_CONFLICT)

        try:
            response = super().handle_exception(exc)
        except Exception as e:
            import traceback

            logging.exception("Unhandled exception in API view")
            if settings.DEBUG:
                return self.error_response(
                    f"Server error: {str(e)}",
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    details=traceback.format_exc(),
                )
            return self.error_response("Server error", status.HTTP_500_INTERNAL_SERVER_ERROR)

        if response is None:
            if settings.DEBUG:
                return self.error_response("Server error: Response is None", status.HTTP_500_INTERNAL_SERVER_ERROR)
            return self.error_response("Server error", status.HTTP_500_INTERNAL_SERVER_ERROR)
        if isinstance(exc, ValidationError):
            data = response.data or {}
            errors = data.get("errors", data)
            code = data.get("code", getattr(exc, "default_code", "invalid"))
            return Response({"error": "Validation error", "code": code, "errors": errors}, status=response.status_code)
        if isinstance(exc, NotFound):
            return self.error_response("Not found", response.status_code)
        if isinstance(response.data, dict) and "detail" in response.data:
            return self.error_response(response.data["detail"], response.status_code)
        return response


class StandardResultsSetPagination(pagination.PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


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

    def get_permissions(self):
        """Only staff or admin-group members can create/update/delete document types."""
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), IsStaffOrAdminGroup()]
        return super().get_permissions()

    @extend_schema(summary="Check if a document type can be deleted", responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["get"], url_path="can-delete")
    def can_delete(self, request, pk=None):
        """Check if document type can be safely deleted."""
        from django.db.models import Q
        from products.models.product import Product

        document_type = self.get_object()

        # Check if any product uses this document type
        products = Product.objects.filter(
            Q(required_documents__icontains=document_type.name) | Q(optional_documents__icontains=document_type.name)
        )

        # Double check to avoid partial matches
        for product in products:
            req = [d.strip() for d in product.required_documents.split(",") if d.strip()]
            opt = [d.strip() for d in product.optional_documents.split(",") if d.strip()]
            if document_type.name in req or document_type.name in opt:
                return Response(
                    {
                        "canDelete": False,
                        "message": f"Cannot delete '{document_type.name}' because it is used in one or more products.",
                        "warning": None,
                    }
                )

        return Response({"canDelete": True, "message": None, "warning": None})


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
            customer.doc_applications.filter(invoice_applications__isnull=True)
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
            customer.doc_applications.select_related("customer", "product")
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
    authenticated_lookup_actions = frozenset({"list", "get_product_by_id", "get_products_by_product_type"})

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

    def get_queryset(self):
        queryset = super().get_queryset()
        product_type = self.request.query_params.get("product_type")
        if product_type:
            queryset = queryset.filter(product_type=product_type)
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["get"], url_path="can-delete")
    def can_delete(self, request, pk=None):
        product = self.get_object()
        can_delete, message = product.can_be_deleted()
        return Response({"can_delete": can_delete, "message": message})

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
        products = Product.objects.filter(product_type=product_type)
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

        existing_job = _latest_inflight_job(
            AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
            ASYNC_JOB_INFLIGHT_STATUSES,
        )
        if existing_job:
            _observe_async_guard_event(
                namespace=namespace,
                event="deduplicated",
                user=request.user,
                job_id=str(existing_job.id),
                status_code=status.HTTP_202_ACCEPTED,
            )
            return Response(
                {
                    "job_id": str(existing_job.id),
                    "status": existing_job.status,
                    "progress": existing_job.progress,
                    "queued": False,
                    "deduplicated": True,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        lock_key, lock_token = _get_enqueue_guard_token(namespace=namespace, user=request.user)
        if not lock_token:
            _observe_async_guard_event(
                namespace=namespace,
                event="lock_contention",
                user=request.user,
                warning=True,
            )
            existing_job = _latest_inflight_job(
                AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
                ASYNC_JOB_INFLIGHT_STATUSES,
            )
            if existing_job:
                _observe_async_guard_event(
                    namespace=namespace,
                    event="deduplicated",
                    user=request.user,
                    job_id=str(existing_job.id),
                    status_code=status.HTTP_202_ACCEPTED,
                )
                return Response(
                    {
                        "job_id": str(existing_job.id),
                        "status": existing_job.status,
                        "progress": existing_job.progress,
                        "queued": False,
                        "deduplicated": True,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
            _observe_async_guard_event(
                namespace=namespace,
                event="guard_429",
                user=request.user,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                warning=True,
            )
            return self.error_response(
                "Product export trigger is already being processed. Please retry in a moment.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            existing_job = _latest_inflight_job(
                AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
                ASYNC_JOB_INFLIGHT_STATUSES,
            )
            if existing_job:
                _observe_async_guard_event(
                    namespace=namespace,
                    event="deduplicated",
                    user=request.user,
                    job_id=str(existing_job.id),
                    status_code=status.HTTP_202_ACCEPTED,
                )
                return Response(
                    {
                        "job_id": str(existing_job.id),
                        "status": existing_job.status,
                        "progress": existing_job.progress,
                        "queued": False,
                        "deduplicated": True,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            job = AsyncJob.objects.create(
                task_name=namespace,
                status=AsyncJob.STATUS_PENDING,
                progress=0,
                message="Queued product export...",
                created_by=request.user,
            )

            run_product_export_job(str(job.id), request.user.id if request.user else None, query)
        finally:
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

        existing_job = _latest_inflight_job(
            AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
            ASYNC_JOB_INFLIGHT_STATUSES,
        )
        if existing_job:
            _observe_async_guard_event(
                namespace=namespace,
                event="deduplicated",
                user=request.user,
                job_id=str(existing_job.id),
                status_code=status.HTTP_202_ACCEPTED,
            )
            return Response(
                {
                    "job_id": str(existing_job.id),
                    "status": existing_job.status,
                    "progress": existing_job.progress,
                    "queued": False,
                    "deduplicated": True,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        lock_key, lock_token = _get_enqueue_guard_token(namespace=namespace, user=request.user)
        if not lock_token:
            _observe_async_guard_event(
                namespace=namespace,
                event="lock_contention",
                user=request.user,
                warning=True,
            )
            existing_job = _latest_inflight_job(
                AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
                ASYNC_JOB_INFLIGHT_STATUSES,
            )
            if existing_job:
                _observe_async_guard_event(
                    namespace=namespace,
                    event="deduplicated",
                    user=request.user,
                    job_id=str(existing_job.id),
                    status_code=status.HTTP_202_ACCEPTED,
                )
                return Response(
                    {
                        "job_id": str(existing_job.id),
                        "status": existing_job.status,
                        "progress": existing_job.progress,
                        "queued": False,
                        "deduplicated": True,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
            _observe_async_guard_event(
                namespace=namespace,
                event="guard_429",
                user=request.user,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                warning=True,
            )
            return self.error_response(
                "Product import trigger is already being processed. Please retry in a moment.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            existing_job = _latest_inflight_job(
                AsyncJob.objects.filter(task_name=namespace, created_by=request.user),
                ASYNC_JOB_INFLIGHT_STATUSES,
            )
            if existing_job:
                _observe_async_guard_event(
                    namespace=namespace,
                    event="deduplicated",
                    user=request.user,
                    job_id=str(existing_job.id),
                    status_code=status.HTTP_202_ACCEPTED,
                )
                return Response(
                    {
                        "job_id": str(existing_job.id),
                        "status": existing_job.status,
                        "progress": existing_job.progress,
                        "queued": False,
                        "deduplicated": True,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

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

        existing_job = _latest_inflight_job(
            InvoiceDownloadJob.objects.filter(
                invoice=invoice,
                format_type=format_type,
                created_by=request.user,
            ),
            QUEUE_JOB_INFLIGHT_STATUSES,
        )
        if existing_job:
            _observe_async_guard_event(
                namespace=namespace,
                event="deduplicated",
                user=request.user,
                job_id=str(existing_job.id),
                status_code=status.HTTP_202_ACCEPTED,
            )
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
        lock_key, lock_token = _get_enqueue_guard_token(
            namespace=namespace,
            user=request.user,
            scope=scope,
        )
        if not lock_token:
            _observe_async_guard_event(
                namespace=namespace,
                event="lock_contention",
                user=request.user,
                warning=True,
                detail=scope,
            )
            existing_job = _latest_inflight_job(
                InvoiceDownloadJob.objects.filter(
                    invoice=invoice,
                    format_type=format_type,
                    created_by=request.user,
                ),
                QUEUE_JOB_INFLIGHT_STATUSES,
            )
            if existing_job:
                _observe_async_guard_event(
                    namespace=namespace,
                    event="deduplicated",
                    user=request.user,
                    job_id=str(existing_job.id),
                    status_code=status.HTTP_202_ACCEPTED,
                )
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
            _observe_async_guard_event(
                namespace=namespace,
                event="guard_429",
                user=request.user,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                warning=True,
                detail=scope,
            )
            return self.error_response(
                "Invoice download trigger is already being processed. Please retry in a moment.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            existing_job = _latest_inflight_job(
                InvoiceDownloadJob.objects.filter(
                    invoice=invoice,
                    format_type=format_type,
                    created_by=request.user,
                ),
                QUEUE_JOB_INFLIGHT_STATUSES,
            )
            if existing_job:
                _observe_async_guard_event(
                    namespace=namespace,
                    event="deduplicated",
                    user=request.user,
                    job_id=str(existing_job.id),
                    status_code=status.HTTP_202_ACCEPTED,
                )
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

        response = StreamingHttpResponse(self._stream_download_job(request, job), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _stream_download_job(self, request, job):
        last_progress = None

        yield self._send_download_event(
            "start", {"message": "Starting invoice generation...", "progress": job.progress}
        )

        while True:
            job.refresh_from_db()

            if last_progress != job.progress:
                yield self._send_download_event(
                    "progress",
                    {"progress": job.progress, "status": job.status},
                )
                last_progress = job.progress

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
                )
                break

            if job.status == InvoiceDownloadJob.STATUS_FAILED:
                yield self._send_download_event(
                    "error",
                    {"message": job.error_message or "Invoice generation failed", "status": job.status},
                )
                break

            yield ": keep-alive\n\n"
            time.sleep(0.5)

    @staticmethod
    def _send_download_event(event_type, data):
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

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
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error processing upload: {str(e)}", exc_info=True)
            return self.error_response(
                f"Server error: {str(e)}",
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

        existing_job = _latest_inflight_job(
            InvoiceImportJob.objects.filter(created_by=request.user),
            QUEUE_JOB_INFLIGHT_STATUSES,
        )
        if existing_job:
            _observe_async_guard_event(
                namespace=namespace,
                event="deduplicated",
                user=request.user,
                job_id=str(existing_job.id),
                status_code=status.HTTP_202_ACCEPTED,
            )
            response = StreamingHttpResponse(
                self._stream_import_job(existing_job.id, request),
                content_type="text/event-stream",
            )
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"
            return response

        lock_key, lock_token = _get_enqueue_guard_token(namespace=namespace, user=request.user)
        if not lock_token:
            _observe_async_guard_event(
                namespace=namespace,
                event="lock_contention",
                user=request.user,
                warning=True,
            )
            existing_job = _latest_inflight_job(
                InvoiceImportJob.objects.filter(created_by=request.user),
                QUEUE_JOB_INFLIGHT_STATUSES,
            )
            if existing_job:
                _observe_async_guard_event(
                    namespace=namespace,
                    event="deduplicated",
                    user=request.user,
                    job_id=str(existing_job.id),
                    status_code=status.HTTP_202_ACCEPTED,
                )
                response = StreamingHttpResponse(
                    self._stream_import_job(existing_job.id, request),
                    content_type="text/event-stream",
                )
                response["Cache-Control"] = "no-cache"
                response["X-Accel-Buffering"] = "no"
                return response
            _observe_async_guard_event(
                namespace=namespace,
                event="guard_429",
                user=request.user,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                warning=True,
            )
            return self.error_response(
                "Invoice import trigger is already being processed. Please retry in a moment.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            existing_job = _latest_inflight_job(
                InvoiceImportJob.objects.filter(created_by=request.user),
                QUEUE_JOB_INFLIGHT_STATUSES,
            )
            if existing_job:
                _observe_async_guard_event(
                    namespace=namespace,
                    event="deduplicated",
                    user=request.user,
                    job_id=str(existing_job.id),
                    status_code=status.HTTP_202_ACCEPTED,
                )
                response = StreamingHttpResponse(
                    self._stream_import_job(existing_job.id, request),
                    content_type="text/event-stream",
                )
                response["Cache-Control"] = "no-cache"
                response["X-Accel-Buffering"] = "no"
                return response

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
            self._stream_import_job(job.id, request),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _stream_import_job(self, job_id, request=None):
        """Stream SSE updates for a running Huey import job."""
        from invoices.models import InvoiceImportJob

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

        while True:
            job.refresh_from_db()
            items = list(job.items.all().order_by("sort_index"))

            for item in items:
                from invoices.models import InvoiceImportItem

                state = sent_states.get(item.id, {"file_start": False, "parsing": False, "done": False})

                if item.status == InvoiceImportItem.STATUS_PROCESSING and not state["file_start"]:
                    yield self._send_import_event(
                        "file_start",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "message": f"Processing {item.filename}...",
                        },
                    )
                    state["file_start"] = True

                if (
                    item.status == InvoiceImportItem.STATUS_PROCESSING
                    and item.result
                    and item.result.get("stage") == "parsing"
                    and not state["parsing"]
                ):
                    yield self._send_import_event(
                        "parsing",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "message": f"Parsing {item.filename} with AI...",
                        },
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

                    yield self._send_import_event(
                        event_type,
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "message": message,
                            "result": result_data,
                        },
                    )
                    state["done"] = True

                sent_states[item.id] = state

            if job.processed_files >= job.total_files and all(state["done"] for state in sent_states.values()):
                summary = self._build_import_summary(job, items)
                yield self._send_import_event(
                    "complete",
                    {
                        "message": f"Import complete: {summary['summary']['imported']} imported, "
                        f"{summary['summary']['duplicates']} duplicates, {summary['summary']['errors']} errors",
                        **summary,
                    },
                )
                break

            yield ": keep-alive\n\n"
            time.sleep(0.5)

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
    def _send_import_event(event_type, data):
        """Format and send an SSE event."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


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
        if self.action == "retrieve":
            return DocApplicationDetailSerializer
        return DocApplicationSerializerWithRelations

    def _serialize_application_detail(self, application):
        detail_instance = (
            self.get_queryset().filter(pk=application.pk).first() if getattr(application, "pk", None) else application
        )
        return DocApplicationDetailSerializer(
            detail_instance or application,
            context={"request": self.request},
        ).data

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
        """Create application synchronously and queue calendar sync in Huey."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = serializer.save()
        self._queue_calendar_sync(application_id=application.id, user_id=request.user.id)
        data = self._serialize_application_detail(application)
        headers = self.get_success_headers(serializer.data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    @extend_schema(responses={200: DocApplicationDetailSerializer})
    def update(self, request, *args, **kwargs):
        """Update application synchronously and queue calendar sync in Huey."""
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
        return Response({"deleted_count": count})

    @action(detail=True, methods=["post"], url_path="advance-workflow")
    @extend_schema(responses={200: DocApplicationDetailSerializer})
    def advance_workflow(self, request, pk=None):
        """Complete current workflow synchronously and queue calendar sync in Huey."""
        from customer_applications.services.application_lifecycle_service import ApplicationLifecycleService

        try:
            application = self.get_object()
        except DocApplication.DoesNotExist:
            return self.error_response("Application not found", status.HTTP_404_NOT_FOUND)

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
        """Delete application synchronously and queue calendar cleanup in Huey."""
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

            previous_workflow.status = DocWorkflow.STATUS_PENDING
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
        if not application.reopen(request.user):
            return self.error_response("Application is not completed", status.HTTP_400_BAD_REQUEST)
        return Response({"success": True})

    @extend_schema(responses=DocApplicationDetailSerializer)
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
        serializer = DocApplicationDetailSerializer(application, context={"request": request})
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

        validate_with_ai = request.data.get("validate_with_ai", "").lower() in ("true", "1", "yes")
        if validate_with_ai and response.status_code == 200:
            document = self.get_object()
            if document.file and document.file.name:
                document.ai_validation_status = Document.AI_VALIDATION_PENDING
                document.ai_validation_result = None
                document.save(update_fields=["ai_validation_status", "ai_validation_result", "updated_at"])
                run_document_validation(document.id)
                # Re-serialize to include pending validation status
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
                "hasOcrCheck": document.doc_type.has_ocr_check if document.doc_type else False,
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
            "ocrCheck": document.ocr_check,
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
        if getattr(self, "action", None) == "status":
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

        existing_job = _latest_inflight_job(
            OCRJob.objects.filter(created_by=request.user),
            QUEUE_JOB_INFLIGHT_STATUSES,
        )
        if existing_job:
            _observe_async_guard_event(
                namespace=namespace,
                event="deduplicated",
                user=request.user,
                job_id=str(existing_job.id),
                status_code=status.HTTP_202_ACCEPTED,
            )
            status_url = request.build_absolute_uri(reverse("api-ocr-status", kwargs={"job_id": str(existing_job.id)}))
            return Response(
                data={
                    "job_id": str(existing_job.id),
                    "status": existing_job.status,
                    "progress": existing_job.progress,
                    "status_url": status_url,
                    "queued": False,
                    "deduplicated": True,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        lock_key, lock_token = _get_enqueue_guard_token(namespace=namespace, user=request.user)
        if not lock_token:
            _observe_async_guard_event(
                namespace=namespace,
                event="lock_contention",
                user=request.user,
                warning=True,
            )
            existing_job = _latest_inflight_job(
                OCRJob.objects.filter(created_by=request.user),
                QUEUE_JOB_INFLIGHT_STATUSES,
            )
            if existing_job:
                _observe_async_guard_event(
                    namespace=namespace,
                    event="deduplicated",
                    user=request.user,
                    job_id=str(existing_job.id),
                    status_code=status.HTTP_202_ACCEPTED,
                )
                status_url = request.build_absolute_uri(
                    reverse("api-ocr-status", kwargs={"job_id": str(existing_job.id)})
                )
                return Response(
                    data={
                        "job_id": str(existing_job.id),
                        "status": existing_job.status,
                        "progress": existing_job.progress,
                        "status_url": status_url,
                        "queued": False,
                        "deduplicated": True,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
            _observe_async_guard_event(
                namespace=namespace,
                event="guard_429",
                user=request.user,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                warning=True,
            )
            return self.error_response(
                "OCR trigger is already being processed. Please retry in a moment.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            existing_job = _latest_inflight_job(
                OCRJob.objects.filter(created_by=request.user),
                QUEUE_JOB_INFLIGHT_STATUSES,
            )
            if existing_job:
                _observe_async_guard_event(
                    namespace=namespace,
                    event="deduplicated",
                    user=request.user,
                    job_id=str(existing_job.id),
                    status_code=status.HTTP_202_ACCEPTED,
                )
                status_url = request.build_absolute_uri(
                    reverse("api-ocr-status", kwargs={"job_id": str(existing_job.id)})
                )
                return Response(
                    data={
                        "job_id": str(existing_job.id),
                        "status": existing_job.status,
                        "progress": existing_job.progress,
                        "status_url": status_url,
                        "queued": False,
                        "deduplicated": True,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

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

            status_url = request.build_absolute_uri(reverse("api-ocr-status", kwargs={"job_id": str(job.id)}))
            return Response(
                data={
                    "job_id": str(job.id),
                    "status": job.status,
                    "progress": job.progress,
                    "status_url": status_url,
                    "queued": True,
                    "deduplicated": False,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception as e:
            errMsg = e.args[0] if e.args else str(e)
            return self.error_response(errMsg, status.HTTP_400_BAD_REQUEST)
        finally:
            release_enqueue_guard(lock_key, lock_token)

    @action(detail=False, methods=["get"], url_path=r"status/(?P<job_id>[^/.]+)")
    def status(self, request, job_id=None):
        job = restrict_to_owner_unless_privileged(OCRJob.objects.filter(id=job_id), request.user).first()
        if not job:
            return self.error_response("OCR job not found", status.HTTP_404_NOT_FOUND)

        response_data = {
            "job_id": str(job.id),
            "status": job.status,
            "progress": job.progress,
        }

        if job.status == OCRJob.STATUS_COMPLETED:
            if job.result:
                result_data = dict(job.result)
                preview_storage_path = result_data.get("preview_storage_path")
                if preview_storage_path:
                    try:
                        preview_url = get_ocr_preview_url(preview_storage_path)
                    except Exception:
                        preview_url = None
                    if preview_url:
                        result_data["preview_url"] = preview_url
                        result_data["previewUrl"] = preview_url
                response_data.update(result_data)
            if job.save_session and not job.session_saved and job.result:
                request.session["file_path"] = job.file_path
                request.session["file_url"] = job.file_url
                request.session["mrz_data"] = job.result.get("mrz_data")
                request.session.save()
                job.session_saved = True
                job.save(update_fields=["session_saved", "updated_at"])
        elif job.status == OCRJob.STATUS_FAILED:
            response_data["error"] = job.error_message or "OCR job failed"

        return Response(data=response_data, status=status.HTTP_200_OK)


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
        if getattr(self, "action", None) == "status":
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
        }

        file_type = mimetypes.guess_type(file.name)[0]
        file_ext = os.path.splitext(file.name)[1].lower()
        if not file_type:
            file_type = valid_file_types.get(file_ext)

        if file_ext not in valid_file_types or file_type not in valid_file_types.values():
            return self.error_response(
                "File format not supported. Only PDF, Excel, and Word are accepted!",
                status.HTTP_400_BAD_REQUEST,
            )

        existing_job = _latest_inflight_job(
            DocumentOCRJob.objects.filter(created_by=request.user),
            QUEUE_JOB_INFLIGHT_STATUSES,
        )
        if existing_job:
            _observe_async_guard_event(
                namespace=namespace,
                event="deduplicated",
                user=request.user,
                job_id=str(existing_job.id),
                status_code=status.HTTP_202_ACCEPTED,
            )
            status_url = request.build_absolute_uri(
                reverse("api-document-ocr-status", kwargs={"job_id": str(existing_job.id)})
            )
            return Response(
                data={
                    "job_id": str(existing_job.id),
                    "status": existing_job.status,
                    "progress": existing_job.progress,
                    "status_url": status_url,
                    "queued": False,
                    "deduplicated": True,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        lock_key, lock_token = _get_enqueue_guard_token(namespace=namespace, user=request.user)
        if not lock_token:
            _observe_async_guard_event(
                namespace=namespace,
                event="lock_contention",
                user=request.user,
                warning=True,
            )
            existing_job = _latest_inflight_job(
                DocumentOCRJob.objects.filter(created_by=request.user),
                QUEUE_JOB_INFLIGHT_STATUSES,
            )
            if existing_job:
                _observe_async_guard_event(
                    namespace=namespace,
                    event="deduplicated",
                    user=request.user,
                    job_id=str(existing_job.id),
                    status_code=status.HTTP_202_ACCEPTED,
                )
                status_url = request.build_absolute_uri(
                    reverse("api-document-ocr-status", kwargs={"job_id": str(existing_job.id)})
                )
                return Response(
                    data={
                        "job_id": str(existing_job.id),
                        "status": existing_job.status,
                        "progress": existing_job.progress,
                        "status_url": status_url,
                        "queued": False,
                        "deduplicated": True,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
            _observe_async_guard_event(
                namespace=namespace,
                event="guard_429",
                user=request.user,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                warning=True,
            )
            return self.error_response(
                "Document OCR trigger is already being processed. Please retry in a moment.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            existing_job = _latest_inflight_job(
                DocumentOCRJob.objects.filter(created_by=request.user),
                QUEUE_JOB_INFLIGHT_STATUSES,
            )
            if existing_job:
                _observe_async_guard_event(
                    namespace=namespace,
                    event="deduplicated",
                    user=request.user,
                    job_id=str(existing_job.id),
                    status_code=status.HTTP_202_ACCEPTED,
                )
                status_url = request.build_absolute_uri(
                    reverse("api-document-ocr-status", kwargs={"job_id": str(existing_job.id)})
                )
                return Response(
                    data={
                        "job_id": str(existing_job.id),
                        "status": existing_job.status,
                        "progress": existing_job.progress,
                        "status_url": status_url,
                        "queued": False,
                        "deduplicated": True,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

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
                request_params={"file_type": file_type},
            )
            run_document_ocr_job(str(job.id))

            status_url = request.build_absolute_uri(reverse("api-document-ocr-status", kwargs={"job_id": str(job.id)}))
            return Response(
                data={
                    "job_id": str(job.id),
                    "status": job.status,
                    "progress": job.progress,
                    "status_url": status_url,
                    "queued": True,
                    "deduplicated": False,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception as e:
            errMsg = e.args[0] if e.args else str(e)
            return self.error_response(errMsg, status.HTTP_400_BAD_REQUEST)
        finally:
            release_enqueue_guard(lock_key, lock_token)

    @action(detail=False, methods=["get"], url_path=r"status/(?P<job_id>[^/.]+)")
    def status(self, request, job_id=None):
        job = restrict_to_owner_unless_privileged(DocumentOCRJob.objects.filter(id=job_id), request.user).first()
        if not job:
            return self.error_response("Document OCR job not found", status.HTTP_404_NOT_FOUND)

        response_data = {
            "job_id": str(job.id),
            "status": job.status,
            "progress": job.progress,
        }

        if job.status == DocumentOCRJob.STATUS_COMPLETED:
            response_data["text"] = job.result_text
        elif job.status == DocumentOCRJob.STATUS_FAILED:
            response_data["error"] = job.error_message or "Document OCR job failed"

        return Response(data=response_data, status=status.HTTP_200_OK)


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
                return Response({"due_date": due_date})
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
@throttle_classes([ScopedRateThrottle])
def exec_cron_jobs(request):
    """
    Execute cron jobs via Huey
    """
    request.throttle_scope = "cron"
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
    if not getattr(settings, "MOCK_AUTH_ENABLED", False):
        return Response(
            {
                "code": "mock_auth_disabled",
                "errors": {"detail": ["Mock authentication is disabled."]},
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    username = getattr(settings, "MOCK_AUTH_USERNAME", "mockuser")
    email = getattr(settings, "MOCK_AUTH_EMAIL", "mock@example.com")

    return Response(
        {
            "sub": username,
            "username": username,
            "email": email,
            "is_superuser": getattr(settings, "MOCK_AUTH_IS_SUPERUSER", True),
            "is_staff": getattr(settings, "MOCK_AUTH_IS_STAFF", True),
            "groups": getattr(settings, "MOCK_AUTH_GROUPS", []),
            "roles": getattr(settings, "MOCK_AUTH_ROLES", []),
        }
    )


@api_view(["POST"])
@csrf_exempt
@authentication_classes([JwtOrMockAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def customer_quick_create(request):
    """
    Quick create a customer with minimal required fields
    """
    request.throttle_scope = "quick_create"
    try:
        serializer = CustomerQuickCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        customer = create_quick_customer(validated_data=serializer.validated_data)

        return Response(
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
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        # Handle validation errors
        error_msg = str(e)
        if hasattr(e, "message_dict"):
            # Django ValidationError
            return Response({"success": False, "errors": e.message_dict}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"success": False, "error": error_msg}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@csrf_exempt
@authentication_classes([JwtOrMockAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def customer_application_quick_create(request):
    """
    Quick create a customer application with documents and workflows
    """
    request.throttle_scope = "quick_create"
    try:
        serializer = CustomerApplicationQuickCreateSerializer(data=request.data)
        if not serializer.is_valid():
            if "doc_date" in serializer.errors:
                return Response(
                    {"success": False, "error": "Invalid date format. Use YYYY-MM-DD or DD/MM/YYYY."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if "customer" in serializer.errors or "product" in serializer.errors:
                return Response(
                    {"success": False, "error": "Customer or product not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        doc_app = create_quick_customer_application(
            customer=validated_data.get("customer"),
            product=validated_data.get("product"),
            doc_date=validated_data.get("doc_date"),
            notes=validated_data.get("notes", ""),
            created_by=request.user,
        )

        return Response(
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
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        # Handle validation errors
        import logging

        error_msg = str(e)
        logging.getLogger(__name__).exception(f"Error in customer_application_quick_create: {error_msg}")

        if hasattr(e, "message_dict"):
            # Django ValidationError
            return Response({"success": False, "errors": e.message_dict}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"success": False, "error": error_msg}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@csrf_exempt
@authentication_classes([JwtOrMockAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated, IsAdminOrManagerGroup])
@throttle_classes([ScopedRateThrottle])
def product_quick_create(request):
    """
    Quick create a product with minimal required fields
    """
    request.throttle_scope = "quick_create"
    try:
        serializer = ProductQuickCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        product = create_quick_product(validated_data=serializer.validated_data, user=request.user)

        return Response(
            {
                "success": True,
                "product": {
                    "id": product.id,
                    "name": product.name,
                    "code": product.code,
                    "product_type": product.product_type,
                    "base_price": product.base_price,
                    "retail_price": product.retail_price,
                    "created_at": product.created_at,
                    "updated_at": product.updated_at,
                    "created_by": product.created_by_id,
                    "updated_by": product.updated_by_id,
                },
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        # Handle validation errors
        error_msg = str(e)
        if hasattr(e, "message_dict"):
            # Django ValidationError
            return Response({"success": False, "errors": e.message_dict}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"success": False, "error": error_msg}, status=status.HTTP_400_BAD_REQUEST)


class WorkflowNotificationViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStaffOrAdminGroup]
    serializer_class = WorkflowNotificationSerializer
    queryset = WorkflowNotification.objects.select_related("doc_application", "doc_workflow").all()
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["recipient", "subject", "status", "doc_application__id"]
    ordering = ["-id"]

    @action(detail=True, methods=["post"], url_path="resend")
    def resend(self, request, pk=None):
        from customer_applications.tasks import schedule_whatsapp_status_poll
        from notifications.services.providers import NotificationDispatcher, is_queued_provider_result

        notification = self.get_object()
        if notification.status == WorkflowNotification.STATUS_CANCELLED:
            return self.error_response("Cancelled notifications cannot be resent.", status.HTTP_400_BAD_REQUEST)

        attempted_at = timezone.now()
        try:
            result = NotificationDispatcher().send(
                notification.channel,
                notification.recipient,
                notification.subject,
                notification.body,
            )
            notification.provider_message = str(result)
            if is_queued_provider_result(notification.channel, result):
                notification.status = WorkflowNotification.STATUS_PENDING
                notification.sent_at = None
                notification.scheduled_for = attempted_at
                if notification.channel == WorkflowNotification.CHANNEL_WHATSAPP:
                    notification.external_reference = ""
                notification.save(
                    update_fields=[
                        "status",
                        "sent_at",
                        "scheduled_for",
                        "provider_message",
                        "external_reference",
                        "updated_at",
                    ]
                )
            else:
                notification.scheduled_for = attempted_at
                if notification.channel == WorkflowNotification.CHANNEL_WHATSAPP:
                    # Meta accepted response is not delivery confirmation.
                    notification.status = WorkflowNotification.STATUS_PENDING
                    notification.sent_at = None
                    notification.external_reference = str(result)
                else:
                    notification.status = WorkflowNotification.STATUS_SENT
                    notification.sent_at = attempted_at
                notification.save(
                    update_fields=[
                        "status",
                        "sent_at",
                        "scheduled_for",
                        "provider_message",
                        "external_reference",
                        "updated_at",
                    ]
                )
                if notification.channel == WorkflowNotification.CHANNEL_WHATSAPP and notification.external_reference:
                    schedule_whatsapp_status_poll(notification_id=notification.id, delay_seconds=5)
        except Exception as exc:
            notification.status = WorkflowNotification.STATUS_FAILED
            notification.sent_at = None
            notification.scheduled_for = attempted_at
            notification.provider_message = str(exc)
            if notification.channel == WorkflowNotification.CHANNEL_WHATSAPP:
                notification.external_reference = ""
            notification.save(
                update_fields=[
                    "status",
                    "sent_at",
                    "scheduled_for",
                    "provider_message",
                    "external_reference",
                    "updated_at",
                ]
            )
            return self.error_response(str(exc), status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(notification).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        notification = self.get_object()
        notification.status = WorkflowNotification.STATUS_CANCELLED
        notification.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(notification).data)


class CalendarReminderViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CalendarReminderSerializer
    queryset = CalendarReminder.objects.select_related("user", "created_by", "calendar_event").all()
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["content", "status", "user__username", "user__first_name", "user__last_name", "user__email"]
    ordering_fields = ["scheduled_for", "created_at", "updated_at", "status_rank"]

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return CalendarReminderCreateSerializer
        if self.action == "bulk_create":
            return CalendarReminderBulkCreateSerializer
        if self.action == "inbox_mark_read":
            return CalendarReminderInboxMarkReadSerializer
        if self.action == "inbox_snooze":
            return CalendarReminderInboxSnoozeSerializer
        return CalendarReminderSerializer

    @staticmethod
    def _safe_positive_int(raw_value, *, default: int, minimum: int = 1, maximum: int | None = None) -> int:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = default

        value = max(value, minimum)
        if maximum is not None:
            value = min(value, maximum)
        return value

    @staticmethod
    def _parse_iso_date(raw_value: str | None):
        if not raw_value:
            return None
        try:
            return datetime.strptime(raw_value.strip(), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .filter(created_by=self.request.user)
            .annotate(
                status_rank=Case(
                    When(status=CalendarReminder.STATUS_PENDING, then=0),
                    When(status=CalendarReminder.STATUS_SENT, then=1),
                    When(status=CalendarReminder.STATUS_FAILED, then=2),
                    default=99,
                    output_field=IntegerField(),
                )
            )
        )

        raw_status = self.request.query_params.get("status")
        if raw_status:
            requested_statuses = [value.strip() for value in raw_status.split(",") if value.strip()]
            allowed_statuses = {choice[0] for choice in CalendarReminder.STATUS_CHOICES}
            statuses = [value for value in requested_statuses if value in allowed_statuses]
            if statuses:
                queryset = queryset.filter(status__in=statuses)

        created_from = self._parse_iso_date(
            self.request.query_params.get("created_from")
            or self.request.query_params.get("createdFrom")
            or self.request.query_params.get("date_from")
            or self.request.query_params.get("dateFrom")
        )
        if created_from:
            queryset = queryset.filter(created_at__date__gte=created_from)

        created_to = self._parse_iso_date(
            self.request.query_params.get("created_to")
            or self.request.query_params.get("createdTo")
            or self.request.query_params.get("date_to")
            or self.request.query_params.get("dateTo")
        )
        if created_to:
            queryset = queryset.filter(created_at__date__lte=created_to)

        if not self.request.query_params.get("ordering"):
            queryset = queryset.order_by("status_rank", "-scheduled_for", "-id")

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target_user_id = int(data.get("user_id") or request.user.id)
        reminders = CalendarReminderService().create_for_users(
            created_by=request.user,
            user_ids=[target_user_id],
            reminder_date=data["reminder_date"],
            reminder_time=data["reminder_time"],
            timezone_name=data["timezone"],
            content=data["content"],
            calendar_event_id=data.get("calendar_event_id"),
        )
        result = CalendarReminderSerializer(reminders[0], context=self.get_serializer_context())
        headers = self.get_success_headers(result.data)
        return Response(result.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        serializer = self.get_serializer(instance=instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        calendar_event_id = data["calendar_event_id"] if "calendar_event_id" in data else instance.calendar_event_id

        updated = CalendarReminderService().apply_update(
            reminder=instance,
            reminder_date=data.get("reminder_date", instance.reminder_date),
            reminder_time=data.get("reminder_time", instance.reminder_time),
            timezone_name=data.get("timezone", instance.timezone),
            content=data.get("content", instance.content),
            user_id=data.get("user_id"),
            calendar_event_id=calendar_event_id,
        )
        result = CalendarReminderSerializer(updated, context=self.get_serializer_context())
        return Response(result.data)

    @extend_schema(request=CalendarReminderBulkCreateSerializer, responses={201: CalendarReminderSerializer(many=True)})
    @action(detail=False, methods=["post"], url_path="bulk-create")
    def bulk_create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        reminders = CalendarReminderService().create_for_users(
            created_by=request.user,
            user_ids=data["user_ids"],
            reminder_date=data["reminder_date"],
            reminder_time=data["reminder_time"],
            timezone_name=data["timezone"],
            content=data["content"],
            calendar_event_id=data.get("calendar_event_id"),
        )
        return Response(
            CalendarReminderSerializer(reminders, many=True, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="inbox")
    def inbox(self, request):
        today = timezone.localdate()
        limit = self._safe_positive_int(request.query_params.get("limit"), default=20, minimum=1, maximum=100)

        today_queryset = (
            CalendarReminder.objects.select_related("user", "created_by", "calendar_event")
            .filter(
                user=request.user,
                status=CalendarReminder.STATUS_SENT,
                sent_at__date=today,
            )
            .order_by("-sent_at", "-id")
        )
        unread_count = today_queryset.filter(read_at__isnull=True).count()
        payload = CalendarReminderSerializer(
            today_queryset[:limit], many=True, context=self.get_serializer_context()
        ).data
        return Response(
            {
                "date": str(today),
                "unreadCount": unread_count,
                "today": payload,
            }
        )

    @action(detail=False, methods=["post"], url_path="inbox/mark-read")
    def inbox_mark_read(self, request):
        serializer = self.get_serializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data.get("ids") or []
        device_label = (serializer.validated_data.get("device_label") or "").strip()

        today = timezone.localdate()
        now = timezone.now()
        unread_queryset = CalendarReminder.objects.filter(
            user=request.user,
            status=CalendarReminder.STATUS_SENT,
            sent_at__date=today,
            read_at__isnull=True,
        )
        target_queryset = unread_queryset.filter(id__in=ids) if ids else unread_queryset
        if device_label:
            updated = target_queryset.update(read_at=now, read_device_label=device_label, updated_at=now)
        else:
            updated = target_queryset.update(read_at=now, updated_at=now)
        unread_count = CalendarReminder.objects.filter(
            user=request.user,
            status=CalendarReminder.STATUS_SENT,
            sent_at__date=today,
            read_at__isnull=True,
        ).count()
        return Response({"updated": updated, "unreadCount": unread_count})

    @action(detail=False, methods=["post"], url_path="inbox/snooze")
    def inbox_snooze(self, request):
        serializer = self.get_serializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)

        reminder_id = serializer.validated_data["id"]
        minutes = serializer.validated_data.get("minutes", 15)

        reminder = CalendarReminder.objects.filter(
            id=reminder_id,
            user=request.user,
            status=CalendarReminder.STATUS_SENT,
            read_at__isnull=True,
        ).first()
        if reminder is None:
            return self.error_response("Reminder not found or already handled.", status.HTTP_404_NOT_FOUND)

        reminder_timezone_name = reminder.timezone or CalendarReminder.DEFAULT_TIMEZONE
        try:
            reminder_tz = ZoneInfo(reminder_timezone_name)
        except ZoneInfoNotFoundError:
            reminder_tz = ZoneInfo(CalendarReminder.DEFAULT_TIMEZONE)
            reminder_timezone_name = CalendarReminder.DEFAULT_TIMEZONE

        scheduled_local = timezone.localtime(timezone.now() + timedelta(minutes=minutes), reminder_tz)
        reminder.reminder_date = scheduled_local.date()
        reminder.reminder_time = scheduled_local.time().replace(second=0, microsecond=0)
        reminder.timezone = reminder_timezone_name
        reminder.status = CalendarReminder.STATUS_PENDING
        reminder.sent_at = None
        reminder.read_at = None
        reminder.read_device_label = ""
        reminder.delivery_channel = ""
        reminder.delivery_device_label = ""
        reminder.error_message = ""
        reminder.save(
            update_fields=[
                "reminder_date",
                "reminder_time",
                "timezone",
                "scheduled_for",
                "status",
                "sent_at",
                "read_at",
                "delivery_channel",
                "delivery_device_label",
                "error_message",
                "read_device_label",
                "updated_at",
            ]
        )

        today = timezone.localdate()
        unread_count = CalendarReminder.objects.filter(
            user=request.user,
            status=CalendarReminder.STATUS_SENT,
            sent_at__date=today,
            read_at__isnull=True,
        ).count()

        return Response(
            {
                "id": reminder.id,
                "minutes": minutes,
                "scheduledFor": reminder.scheduled_for.isoformat(),
                "unreadCount": unread_count,
            }
        )

    @action(detail=False, methods=["get"], url_path="users")
    def users(self, request):
        user_query = (request.query_params.get("q") or request.query_params.get("search") or "").strip()
        page = self._safe_positive_int(request.query_params.get("page"), default=1, minimum=1)
        page_size = self._safe_positive_int(request.query_params.get("page_size"), default=20, minimum=1, maximum=100)
        offset = (page - 1) * page_size

        User = get_user_model()
        queryset = (
            User.objects.filter(is_active=True)
            .annotate(
                active_push_subscriptions=Count(
                    "web_push_subscriptions",
                    filter=Q(web_push_subscriptions__is_active=True),
                    distinct=True,
                )
            )
            .order_by("first_name", "last_name", "username")
        )
        if user_query:
            queryset = queryset.filter(
                Q(username__icontains=user_query)
                | Q(email__icontains=user_query)
                | Q(first_name__icontains=user_query)
                | Q(last_name__icontains=user_query)
            )

        users = queryset[offset : offset + page_size]
        payload = [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email or "",
                "full_name": user.get_full_name().strip() or user.username,
                "active_push_subscriptions": int(getattr(user, "active_push_subscriptions", 0) or 0),
            }
            for user in users
        ]
        return Response(payload)

    @action(detail=False, methods=["get"], url_path="timezones")
    def timezones(self, request):
        from zoneinfo import available_timezones

        timezone_query = (request.query_params.get("q") or "").strip().lower()
        page = self._safe_positive_int(request.query_params.get("page"), default=1, minimum=1)
        page_size = self._safe_positive_int(request.query_params.get("page_size"), default=50, minimum=1, maximum=200)
        offset = (page - 1) * page_size

        zones = sorted(available_timezones())
        if timezone_query:
            zones = [zone for zone in zones if timezone_query in zone.lower()]

        window = zones[offset : offset + page_size]
        payload = [{"value": zone, "label": zone} for zone in window]
        return Response(payload)

    @action(detail=True, methods=["post"], url_path="ack")
    def ack(self, request, pk=None):
        """Record delivery channel for a reminder (in_app or system)."""
        reminder = self.get_object()
        channel = (request.data.get("channel") or "").strip()
        device_label = (request.data.get("device_label") or "").strip()
        allowed = {CalendarReminder.DELIVERY_IN_APP, CalendarReminder.DELIVERY_SYSTEM}
        if channel not in allowed:
            return self.error_response(
                f"Invalid channel. Must be one of: {', '.join(sorted(allowed))}",
                status.HTTP_400_BAD_REQUEST,
            )
        update_fields: list[str] = []
        if not reminder.delivery_channel:
            reminder.delivery_channel = channel
            update_fields.append("delivery_channel")
        if device_label and (not reminder.delivery_device_label):
            reminder.delivery_device_label = device_label[:255]
            update_fields.append("delivery_device_label")

        if update_fields:
            reminder.save(update_fields=[*update_fields, "updated_at"])
        return Response(
            {
                "id": reminder.id,
                "delivery_channel": reminder.delivery_channel,
                "delivery_device_label": reminder.delivery_device_label,
            }
        )


class PushNotificationViewSet(ApiErrorHandlingMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WebPushSubscriptionSerializer

    def get_serializer_class(self):
        action = getattr(self, "action", None)
        action_map = {
            "subscriptions": WebPushSubscriptionSerializer,
            "register": WebPushSubscriptionUpsertSerializer,
            "unregister": WebPushSubscriptionDeleteSerializer,
            "test": PushNotificationTestSerializer,
            "send_test": AdminPushNotificationSendSerializer,
            "send_test_whatsapp": AdminWhatsappTestSendSerializer,
        }
        return action_map.get(action, self.serializer_class)

    def _ensure_admin(self, request):
        if not request.user or not request.user.is_staff:
            return self.error_response("You do not have permission to perform this action.", status.HTTP_403_FORBIDDEN)
        return None

    @staticmethod
    def _result_payload(result):
        return {
            "sent": result.sent,
            "failed": result.failed,
            "skipped": result.skipped,
            "total": result.total,
        }

    @staticmethod
    def _active_subscription_count(user):
        return WebPushSubscription.objects.filter(user=user, is_active=True).count()

    @staticmethod
    def _subscription_count(user):
        return WebPushSubscription.objects.filter(user=user).count()

    @staticmethod
    def _latest_application_for_test_notification():
        return DocApplication.objects.order_by("-updated_at", "-id").first()

    @action(detail=False, methods=["get"], url_path="subscriptions")
    def subscriptions(self, request):
        queryset = WebPushSubscription.objects.filter(user=request.user).order_by("-updated_at")
        return Response(WebPushSubscriptionSerializer(queryset, many=True).data)

    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        serializer = WebPushSubscriptionUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = cast(dict[str, Any], serializer.validated_data)
        token = data["token"].strip()
        if not token:
            return self.error_response("Token is required", status.HTTP_400_BAD_REQUEST)

        subscription, created = WebPushSubscription.objects.update_or_create(
            token=token,
            defaults={
                "user": request.user,
                "device_label": serializer.validated_data.get("device_label", ""),
                "user_agent": serializer.validated_data.get("user_agent") or request.META.get("HTTP_USER_AGENT", ""),
                "is_active": True,
                "last_error": "",
            },
        )
        payload = WebPushSubscriptionSerializer(subscription).data
        payload["created"] = created
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="unregister")
    def unregister(self, request):
        serializer = WebPushSubscriptionDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = cast(dict[str, Any], serializer.validated_data)
        token = data["token"].strip()
        updated = WebPushSubscription.objects.filter(user=request.user, token=token).update(is_active=False)
        return Response({"updated": updated})

    @action(detail=False, methods=["post"], url_path="test")
    def test(self, request):
        serializer = PushNotificationTestSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)

        data = cast(dict[str, Any], serializer.validated_data)
        active_subscriptions = self._active_subscription_count(request.user)
        if active_subscriptions == 0:
            return self.error_response(
                "No active browser push subscriptions for your user. Open CRM in a browser, allow notifications, then retry.",
                status.HTTP_409_CONFLICT,
                details={
                    "active_subscriptions": 0,
                    "total_subscriptions": self._subscription_count(request.user),
                },
            )
        try:
            result = PushNotificationService().send_to_user(
                user=request.user,
                title=data["title"],
                body=data["body"],
                data=data.get("data") or {},
                link=(data.get("link") or "").strip() or None,
            )
        except FcmConfigurationError as exc:
            return self.error_response(str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)

        payload = self._result_payload(result)
        if result.sent == 0:
            return self.error_response(
                "Push delivery failed for all active subscriptions.",
                status.HTTP_502_BAD_GATEWAY,
                details=payload,
            )
        return Response(payload)

    @action(detail=False, methods=["get"], url_path="users")
    def users(self, request):
        forbidden = self._ensure_admin(request)
        if forbidden is not None:
            return forbidden

        from django.contrib.auth import get_user_model

        User = get_user_model()
        queryset = (
            User.objects.filter(is_active=True)
            .annotate(
                total_push_subscriptions=Count("web_push_subscriptions", distinct=True),
                active_push_subscriptions=Count(
                    "web_push_subscriptions",
                    filter=Q(web_push_subscriptions__is_active=True),
                    distinct=True,
                ),
            )
            .order_by("username")
        )
        payload = [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email or "",
                "full_name": (f"{user.first_name} {user.last_name}".strip() or user.username),
                "active_push_subscriptions": int(getattr(user, "active_push_subscriptions", 0) or 0),
                "total_push_subscriptions": int(getattr(user, "total_push_subscriptions", 0) or 0),
            }
            for user in queryset
        ]
        return Response(payload)

    @action(detail=False, methods=["post"], url_path="send-test")
    def send_test(self, request):
        forbidden = self._ensure_admin(request)
        if forbidden is not None:
            return forbidden

        from django.contrib.auth import get_user_model

        serializer = AdminPushNotificationSendSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)

        User = get_user_model()
        target_user = User.objects.filter(pk=data["user_id"], is_active=True).first()
        if not target_user:
            return self.error_response("Target user not found", status.HTTP_404_NOT_FOUND)

        active_subscriptions = self._active_subscription_count(target_user)
        if active_subscriptions == 0:
            return self.error_response(
                "Target user has no active browser push subscriptions. Open CRM in browser, allow notifications, then retry.",
                status.HTTP_409_CONFLICT,
                details={
                    "target_user_id": target_user.id,
                    "active_subscriptions": 0,
                    "total_subscriptions": self._subscription_count(target_user),
                },
            )

        try:
            result = PushNotificationService().send_to_user(
                user=target_user,
                title=data["title"],
                body=data["body"],
                data=data.get("data") or {},
                link=(data.get("link") or "").strip() or None,
            )
        except FcmConfigurationError as exc:
            return self.error_response(str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)

        payload = self._result_payload(result)
        if result.sent == 0:
            return self.error_response(
                "Push delivery failed for all active subscriptions of the target user.",
                status.HTTP_502_BAD_GATEWAY,
                details=payload,
            )
        return Response(payload)

    @action(detail=False, methods=["post"], url_path="send-test-whatsapp")
    def send_test_whatsapp(self, request):
        forbidden = self._ensure_admin(request)
        if forbidden is not None:
            return forbidden

        serializer = AdminWhatsappTestSendSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        explicit_recipient = str(data.get("to") or "").strip()
        recipient = explicit_recipient or str(getattr(settings, "WHATSAPP_TEST_NUMBER", "") or "").strip()
        if not recipient:
            return self.error_response(
                "No WhatsApp destination configured. Set WHATSAPP_TEST_NUMBER in backend settings or provide 'to'.",
                status.HTTP_400_BAD_REQUEST,
            )

        target_application = self._latest_application_for_test_notification()
        if target_application is None:
            return self.error_response(
                "No applications available to attach a dummy workflow notification.",
                status.HTTP_409_CONFLICT,
            )

        from customer_applications.tasks import schedule_whatsapp_status_poll
        from notifications.services.providers import WhatsappNotificationProvider, is_queued_provider_result

        subject = str(data.get("subject") or "").strip() or "Revis Bali CRM WhatsApp Test"
        body = str(data.get("body") or "").strip() or "WhatsApp test message from Revis Bali CRM."
        whatsapp_body = f"{subject}\n\n{body}" if subject else body

        try:
            message_id = WhatsappNotificationProvider().send(
                recipient=recipient,
                subject=subject,
                body=whatsapp_body,
                prefer_template=False,
                allow_template_fallback=False,
            )
        except Exception as exc:
            return self.error_response(
                f"WhatsApp text send failed: {exc}. "
                "Template fallback is disabled for this test endpoint to preserve exact subject/body.",
                status.HTTP_400_BAD_REQUEST,
            )

        raw_message_id = str(message_id or "").strip()
        queued = is_queued_provider_result("whatsapp", raw_message_id)
        notification = WorkflowNotification.objects.create(
            channel=WorkflowNotification.CHANNEL_WHATSAPP,
            recipient=recipient,
            subject=subject,
            body=body,
            doc_application=target_application,
            doc_workflow=None,
            status=WorkflowNotification.STATUS_PENDING,
            provider_message=raw_message_id,
            external_reference="" if queued else raw_message_id,
            sent_at=None,
            scheduled_for=timezone.now(),
            notification_type="manual_whatsapp_test",
        )
        if notification.external_reference:
            schedule_whatsapp_status_poll(notification_id=notification.id, delay_seconds=5)

        return Response(
            {
                "recipient": recipient,
                "used_default_recipient": explicit_recipient == "",
                "message_id": raw_message_id,
                "workflow_notification_id": notification.id,
                "workflow_notification_status": notification.status,
                "workflow_notification_application_id": notification.doc_application_id,
            }
        )

    @action(detail=False, methods=["post"], url_path="fcm-register-proxy")
    def fcm_register_proxy(self, request):
        """
        Server-side proxy for Firebase Cloud Messaging registration.

        The browser-side Firebase SDK calls fcmregistrations.googleapis.com to exchange
        a Web Push subscription for an FCM token.  On some networks / Chrome configurations
        that endpoint is unreachable from the browser (e.g. QUIC / HTTP3 issues) even
        though the Django server can reach it fine via TCP.  This action forwards the
        registration request from the browser to the real FCM endpoint server-side so the
        browser never needs to reach googleapis.com directly.
        """
        import requests as http_requests

        project_id = getattr(settings, "FCM_PROJECT_ID", "").strip()
        if not project_id:
            return self.error_response("FCM_PROJECT_ID not configured on server", status.HTTP_503_SERVICE_UNAVAILABLE)

        # The Angular fetch interceptor forwards the FIS auth token via X-FCM-Auth.
        # Firebase SDK uses x-goog-firebase-installations-auth (not Authorization).
        fcm_auth = request.META.get("HTTP_X_FCM_AUTH", "").strip()
        api_key = (
            request.META.get("HTTP_X_GOOG_API_KEY", "").strip() or getattr(settings, "FCM_WEB_API_KEY", "").strip()
        )

        if not api_key:
            return self.error_response(
                "Missing required proxy header: X-Goog-Api-Key (and FCM_WEB_API_KEY not configured)",
                status.HTTP_400_BAD_REQUEST,
            )

        url = f"https://fcmregistrations.googleapis.com/v1/projects/{project_id}/registrations"
        fwd_headers: dict = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        if fcm_auth:
            fwd_headers["x-goog-firebase-installations-auth"] = fcm_auth
        try:
            # Use request.body (raw bytes) instead of request.data to avoid
            # DRF's camelCase→snake_case parser corrupting field names.
            resp = http_requests.post(
                url,
                data=request.body,
                headers=fwd_headers,
                timeout=20,
            )
        except http_requests.RequestException as exc:
            logger.error("[fcm_register_proxy] Network error calling FCM registrations: %s", exc)
            return self.error_response(str(exc), status.HTTP_502_BAD_GATEWAY)

        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}

        return Response(body, status=resp.status_code)

    @action(detail=False, methods=["post"], url_path="firebase-install-proxy")
    def firebase_install_proxy(self, request):
        """
        Server-side proxy for Firebase Installations API.

        Handles both FID creation (POST .../installations) and auth-token refresh
        (POST .../installations/{fid}/authTokens:generate) so the browser is never
        required to reach firebaseinstallations.googleapis.com directly.
        """
        import requests as http_requests

        project_id = getattr(settings, "FCM_PROJECT_ID", "").strip()
        if not project_id:
            return self.error_response("FCM_PROJECT_ID not configured on server", status.HTTP_503_SERVICE_UNAVAILABLE)

        # The Angular fetch interceptor passes the original path suffix via a custom header.
        path_suffix = request.META.get("HTTP_X_FIREBASE_PATH", "").strip().lstrip("/")
        api_key = (
            request.META.get("HTTP_X_GOOG_API_KEY", "").strip() or getattr(settings, "FCM_WEB_API_KEY", "").strip()
        )
        firebase_auth = request.META.get("HTTP_X_FIREBASE_AUTH", "").strip()

        if not api_key:
            return self.error_response("Missing required proxy header: X-Goog-Api-Key", status.HTTP_400_BAD_REQUEST)

        base = f"https://firebaseinstallations.googleapis.com/v1/projects/{project_id}"
        url = f"{base}/{path_suffix}" if path_suffix else base

        headers: dict = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        if firebase_auth:
            headers["x-goog-firebase-installations-auth"] = firebase_auth

        try:
            # Use request.body (raw bytes) instead of request.data to avoid
            # DRF's camelCase→snake_case parser corrupting field names.
            resp = http_requests.post(url, data=request.body, headers=headers, timeout=20)
        except http_requests.RequestException as exc:
            logger.error("[firebase_install_proxy] Network error calling Firebase Installations: %s", exc)
            return self.error_response(str(exc), status.HTTP_502_BAD_GATEWAY)

        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}

        return Response(body, status=resp.status_code)


@sse_token_auth_required
def calendar_reminders_stream_sse(request):
    """SSE endpoint for calendar reminder list live updates."""
    user = request.user
    if not (user and user.is_authenticated):
        return JsonResponse({"error": "Authentication required"}, status=403)

    def _latest_reminder_state():
        latest = (
            CalendarReminder.objects.filter(created_by=user)
            .order_by("-updated_at", "-id")
            .values("id", "updated_at")
            .first()
        )
        if not latest:
            return None, None
        updated_at = latest.get("updated_at")
        return latest.get("id"), updated_at.isoformat() if updated_at else None

    def _build_payload(
        *,
        event: str,
        cursor: int,
        last_reminder_id,
        last_updated_at,
        reason: str,
        operation=None,
        changed_reminder_id=None,
    ):
        payload = {
            "event": event,
            "cursor": cursor,
            "lastReminderId": last_reminder_id,
            "lastUpdatedAt": last_updated_at,
            "reason": reason,
        }
        if operation:
            payload["operation"] = operation
        if changed_reminder_id is not None:
            payload["changedReminderId"] = changed_reminder_id
        return payload

    def _safe_owner_id(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def event_stream():
        last_cursor = get_calendar_reminder_stream_cursor()
        last_reminder_id, last_updated_at = _latest_reminder_state()
        keepalive_tick = 0

        snapshot_payload = _build_payload(
            event="calendar_reminders_snapshot",
            cursor=last_cursor,
            last_reminder_id=last_reminder_id,
            last_updated_at=last_updated_at,
            reason="initial",
        )
        yield f"data: {json.dumps(snapshot_payload)}\n\n"

        while True:
            try:
                time.sleep(1)
                keepalive_tick += 1

                current_cursor = get_calendar_reminder_stream_cursor()
                current_reminder_id = last_reminder_id
                current_last_updated_at = last_updated_at
                reason = None
                operation = None
                changed_reminder_id = None

                if current_cursor != last_cursor:
                    event_meta = get_calendar_reminder_stream_last_event() or {}
                    owner_id = _safe_owner_id(event_meta.get("ownerId"))
                    if owner_id is None or owner_id == int(user.id):
                        reason = "signal"
                        if event_meta.get("cursor") == current_cursor:
                            operation = str(event_meta.get("operation") or "").strip() or None
                            raw_changed_id = event_meta.get("reminderId")
                            try:
                                changed_reminder_id = int(raw_changed_id) if raw_changed_id is not None else None
                            except (TypeError, ValueError):
                                changed_reminder_id = None
                        current_reminder_id, current_last_updated_at = _latest_reminder_state()
                    last_cursor = current_cursor
                elif keepalive_tick >= 15:
                    current_reminder_id, current_last_updated_at = _latest_reminder_state()
                    if current_reminder_id != last_reminder_id or current_last_updated_at != last_updated_at:
                        reason = "db_state_change"

                if reason is not None:
                    payload = _build_payload(
                        event="calendar_reminders_changed",
                        cursor=last_cursor,
                        last_reminder_id=current_reminder_id,
                        last_updated_at=current_last_updated_at,
                        reason=reason,
                        operation=operation,
                        changed_reminder_id=changed_reminder_id,
                    )
                    yield f"data: {json.dumps(payload)}\n\n"
                    last_reminder_id = current_reminder_id
                    last_updated_at = current_last_updated_at
                    keepalive_tick = 0
                    continue

                if keepalive_tick >= 15:
                    yield ": keepalive\n\n"
                    keepalive_tick = 0
            except GeneratorExit:
                return
            except Exception as exc:
                yield f"data: {json.dumps({'event': 'calendar_reminders_error', 'error': str(exc)})}\n\n"
                return

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@sse_token_auth_required
def workflow_notifications_stream_sse(request):
    """SSE endpoint for workflow notification center live updates."""
    user = request.user
    if not is_staff_or_admin_group(user):
        return JsonResponse({"error": STAFF_OR_ADMIN_PERMISSION_REQUIRED_ERROR}, status=403)

    def _latest_recent_notification_state():
        cutoff = timezone.now() - timedelta(hours=RECENT_WORKFLOW_NOTIFICATION_WINDOW_HOURS)
        latest = (
            WorkflowNotification.objects.filter(created_at__gte=cutoff)
            .order_by("-updated_at", "-id")
            .values("id", "updated_at")
            .first()
        )
        if not latest:
            return None, None
        updated_at = latest.get("updated_at")
        return latest.get("id"), updated_at.isoformat() if updated_at else None

    def _build_payload(
        *,
        event: str,
        cursor: int,
        last_notification_id,
        last_updated_at,
        reason: str,
        operation=None,
        changed_notification_id=None,
    ):
        payload = {
            "event": event,
            "cursor": cursor,
            "windowHours": RECENT_WORKFLOW_NOTIFICATION_WINDOW_HOURS,
            "lastNotificationId": last_notification_id,
            "lastUpdatedAt": last_updated_at,
            "reason": reason,
        }
        if operation:
            payload["operation"] = operation
        if changed_notification_id is not None:
            payload["changedNotificationId"] = changed_notification_id
        return payload

    def event_stream():
        last_cursor = get_workflow_notification_stream_cursor()
        last_notification_id, last_updated_at = _latest_recent_notification_state()
        keepalive_tick = 0

        snapshot_payload = _build_payload(
            event="workflow_notifications_snapshot",
            cursor=last_cursor,
            last_notification_id=last_notification_id,
            last_updated_at=last_updated_at,
            reason="initial",
        )
        yield f"data: {json.dumps(snapshot_payload)}\n\n"

        while True:
            try:
                time.sleep(1)
                keepalive_tick += 1

                current_cursor = get_workflow_notification_stream_cursor()
                current_notification_id = last_notification_id
                current_last_updated_at = last_updated_at
                reason = None
                operation = None
                changed_notification_id = None

                if current_cursor != last_cursor:
                    reason = "signal"
                    event_meta = get_workflow_notification_stream_last_event() or {}
                    if event_meta.get("cursor") == current_cursor:
                        operation = str(event_meta.get("operation") or "").strip() or None
                        raw_changed_id = event_meta.get("notificationId")
                        if raw_changed_id is not None:
                            try:
                                changed_notification_id = int(raw_changed_id)
                            except (TypeError, ValueError):
                                changed_notification_id = None
                    current_notification_id, current_last_updated_at = _latest_recent_notification_state()
                elif keepalive_tick >= 15:
                    current_notification_id, current_last_updated_at = _latest_recent_notification_state()
                    if current_notification_id != last_notification_id or current_last_updated_at != last_updated_at:
                        reason = "db_state_change"

                if reason is not None:
                    payload = _build_payload(
                        event="workflow_notifications_changed",
                        cursor=current_cursor,
                        last_notification_id=current_notification_id,
                        last_updated_at=current_last_updated_at,
                        reason=reason,
                        operation=operation,
                        changed_notification_id=changed_notification_id,
                    )
                    yield f"data: {json.dumps(payload)}\n\n"
                    last_cursor = current_cursor
                    last_notification_id = current_notification_id
                    last_updated_at = current_last_updated_at
                    keepalive_tick = 0
                    continue

                if keepalive_tick >= 15:
                    yield ": keepalive\n\n"
                    keepalive_tick = 0
            except GeneratorExit:
                return
            except Exception as exc:
                yield f"data: {json.dumps({'event': 'workflow_notifications_error', 'error': str(exc)})}\n\n"
                return

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@sse_token_auth_required
def async_job_status_sse(request, job_id):
    """Generic SSE endpoint for tracking AsyncJob status."""
    job_queryset = restrict_to_owner_unless_privileged(AsyncJob.objects.filter(id=job_id), request.user)
    if not job_queryset.exists():
        return JsonResponse({"error": "Job not found"}, status=404)

    def event_stream():
        last_progress = -1
        last_status = None

        while True:
            try:
                # Refresh from DB
                job = job_queryset.get()

                # Only send if changed
                if job.progress != last_progress or job.status != last_status:
                    data = {
                        "id": str(job.id),
                        "status": job.status,
                        "progress": job.progress,
                        "message": job.message,
                        "result": job.result,
                        "error_message": job.error_message,
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                    last_progress = job.progress
                    last_status = job.status

                # Check for completion
                if job.status in [AsyncJob.STATUS_COMPLETED, AsyncJob.STATUS_FAILED]:
                    break

            except AsyncJob.DoesNotExist:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break

            time.sleep(1)
            yield ": keepalive\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class AsyncJobViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for polling AsyncJob status if SSE is not used."""

    queryset = AsyncJob.objects.all()
    serializer_class = AsyncJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return restrict_to_owner_unless_privileged(super().get_queryset(), self.request.user)
