import json
import logging
import mimetypes
import os
import time
import uuid
from datetime import datetime
from io import BytesIO

from django.conf import settings
from django.contrib.auth import logout as django_logout
from django.core.files.storage import default_storage
from django.db.models import Count, DecimalField, F, OuterRef, Prefetch, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import filters, pagination, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView

from api.serializers import (
    AvatarUploadSerializer,
    ChangePasswordSerializer,
    CountryCodeSerializer,
    CustomerApplicationQuickCreateSerializer,
    CustomerQuickCreateSerializer,
    CustomerSerializer,
    DocApplicationDetailSerializer,
    DocApplicationInvoiceSerializer,
    DocApplicationSerializerWithRelations,
    DocumentMergeSerializer,
    DocumentSerializer,
    DocumentTypeSerializer,
    DocWorkflowSerializer,
    InvoiceCreateUpdateSerializer,
    InvoiceDetailSerializer,
    InvoiceListSerializer,
    PaymentSerializer,
    ProductCreateUpdateSerializer,
    ProductDetailSerializer,
    ProductQuickCreateSerializer,
    ProductSerializer,
    SuratPermohonanCustomerDataSerializer,
    SuratPermohonanRequestSerializer,
    UserProfileSerializer,
    UserSettingsSerializer,
    ordered_document_types,
)
from api.serializers.auth_serializer import CustomTokenObtainSerializer
from business_suite.authentication import JwtOrMockAuthentication
from core.models import CountryCode, DocumentOCRJob, OCRJob, UserProfile, UserSettings
from core.services.document_merger import DocumentMerger, DocumentMergerError
from core.services.quick_create import create_quick_customer, create_quick_customer_application, create_quick_product
from core.tasks.cron_jobs import run_clear_cache_now, run_full_backup_now
from core.tasks.document_ocr import run_document_ocr_job
from core.tasks.ocr import run_ocr_job
from core.utils.dateutils import calculate_due_date
from core.utils.pdf_converter import PDFConverter, PDFConverterError
from customer_applications.models import DocApplication, Document
from customers.models import Customer
from invoices.models import InvoiceDownloadJob
from invoices.models.invoice import Invoice, InvoiceApplication
from invoices.services.InvoiceService import InvoiceService
from invoices.tasks.download_jobs import run_invoice_download_job
from letters.services.LetterService import LetterService
from payments.models import Payment
from products.models import Product
from products.models.document_type import DocumentType
from products.models.task import Task


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def observability_log(request):
    """Proxy endpoint for frontend observability logs.

    Accepts JSON payloads with 'level', 'message', and optional 'metadata'.
    Forwards message to the Django logger and returns 202 Accepted.
    """
    payload = request.data
    logger = logging.getLogger("observability")
    # Log at info level; tests patch Logger.info
    logger.info(payload.get("message", ""), extra={"level": payload.get("level"), "metadata": payload.get("metadata")})
    return Response(status=202)


def parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}


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
        """Only superusers can create/update/delete document types."""
        if self.action in ["create", "update", "partial_update", "destroy"]:
            from django.contrib.auth.decorators import user_passes_test
            from rest_framework.permissions import BasePermission

            class IsSuperuser(BasePermission):
                def has_permission(self, request, view):
                    return request.user and request.user.is_superuser

            return [IsAuthenticated(), IsSuperuser()]
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

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        if not request.user.is_superuser:
            return self.error_response("You do not have permission to perform this action.", status.HTTP_403_FORBIDDEN)

        from core.services.bulk_delete import bulk_delete_customers

        query = (
            request.data.get("search_query") or request.data.get("searchQuery") or request.data.get("query") or ""
        ).strip()
        hide_disabled = parse_bool(request.data.get("hide_disabled") or request.data.get("hideDisabled"), True)

        count = bulk_delete_customers(query=query or None, hide_disabled=hide_disabled)
        return Response({"deleted_count": count})


class ProductViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Product.objects.prefetch_related("tasks").all()
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "code", "description", "product_type"]
    ordering_fields = ["name", "code", "product_type", "base_price", "created_at", "updated_at"]
    ordering = ["name"]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return ProductCreateUpdateSerializer
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductSerializer

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
        if not request.user.is_superuser:
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

        return Response(
            {
                "product": serialized_product.data,
                "required_documents": serialzed_document_types.data,
                "optional_documents": serialzed_optional_document_types.data,
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


class InvoiceViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
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
            queryset.select_related("customer")
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
        if not request.user.is_superuser:
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
        if not request.user.is_superuser:
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
        if not request.user.is_superuser:
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
    @action(detail=True, methods=["post"], url_path="download-async")
    def download_async(self, request, pk=None):
        format_type = (
            request.data.get("file_format")
            or request.data.get("format")
            or request.query_params.get("file_format")
            or "pdf"
        ).lower()

        if format_type not in [InvoiceDownloadJob.FORMAT_DOCX, InvoiceDownloadJob.FORMAT_PDF]:
            return self.error_response("Invalid format. Use 'docx' or 'pdf'.", status.HTTP_400_BAD_REQUEST)

        invoice = self.get_object()

        job = InvoiceDownloadJob.objects.create(
            invoice=invoice,
            status=InvoiceDownloadJob.STATUS_QUEUED,
            progress=0,
            format_type=format_type,
            created_by=request.user,
            request_params={"format": format_type},
        )

        run_invoice_download_job(str(job.id))

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
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"], url_path=r"download-async/status/(?P<job_id>[^/.]+)")
    def download_async_status(self, request, job_id=None):
        try:
            job = InvoiceDownloadJob.objects.select_related("invoice").get(id=job_id)
        except InvoiceDownloadJob.DoesNotExist:
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

    @action(detail=False, methods=["get"], url_path=r"download-async/stream/(?P<job_id>[^/.]+)")
    def download_async_stream(self, request, job_id=None):
        response = StreamingHttpResponse(self._stream_download_job(request, job_id), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _stream_download_job(self, request, job_id):
        last_progress = None
        try:
            job = InvoiceDownloadJob.objects.get(id=job_id)
        except InvoiceDownloadJob.DoesNotExist:
            yield self._send_download_event("error", {"message": "Job not found"})
            return

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

    @action(detail=False, methods=["get"], url_path=r"download-async/file/(?P<job_id>[^/.]+)")
    def download_async_file(self, request, job_id=None):
        try:
            job = InvoiceDownloadJob.objects.select_related("invoice", "invoice__customer").get(id=job_id)
        except InvoiceDownloadJob.DoesNotExist:
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
                "currentModel": getattr(django_settings, "LLM_DEFAULT_MODEL", "google/gemini-2.0-flash-001"),
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
                    "url": reverse("invoice-detail", kwargs={"pk": result.invoice.pk}),
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
    @action(detail=False, methods=["post"], url_path="import/batch", parser_classes=[MultiPartParser, FormParser])
    def import_batch(self, request):
        """Process multiple uploaded invoice files with real-time progress streaming."""
        from django.utils.text import get_valid_filename

        from invoices.models import InvoiceImportItem, InvoiceImportJob
        from invoices.tasks.import_jobs import run_invoice_import_item

        files = request.FILES.getlist("files")
        paid_status_list = request.POST.getlist("paid_status") or request.data.getlist("paidStatus")
        llm_provider = request.POST.get("llm_provider") or request.data.get("llmProvider")
        llm_model = request.POST.get("llm_model") or request.data.get("llmModel")

        if not files:
            return self.error_response("No files uploaded", status.HTTP_400_BAD_REQUEST)

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
    @action(detail=False, methods=["get"], url_path=r"import/status/(?P<job_id>[^/.]+)")
    def import_job_status(self, request, job_id=None):
        """Get status of an import job."""
        from invoices.models import InvoiceImportJob

        try:
            job = InvoiceImportJob.objects.get(id=job_id)
        except InvoiceImportJob.DoesNotExist:
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

    @action(detail=False, methods=["get"], url_path=r"import/stream/(?P<job_id>[^/.]+)")
    def import_job_stream(self, request, job_id=None):
        """Stream SSE updates for a running import job."""
        from invoices.models import InvoiceImportJob

        try:
            job = InvoiceImportJob.objects.get(id=job_id)
        except InvoiceImportJob.DoesNotExist:
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
        from django.db.models import Count, Q

        return (
            DocApplication.objects.select_related("customer", "product")
            .prefetch_related("documents__doc_type", "workflows__task", "invoice_applications__invoice")
            .annotate(
                total_required_documents=Count("documents", filter=Q(documents__required=True)),
                completed_required_documents=Count(
                    "documents", filter=Q(documents__required=True, documents__completed=True)
                ),
            )
        )

    def get_serializer_class(self):
        # Use specialized serializer for create/update actions
        if self.action in ["create", "update", "partial_update"]:
            from api.serializers.doc_application_serializer import DocApplicationCreateUpdateSerializer

            return DocApplicationCreateUpdateSerializer
        if self.action == "retrieve":
            return DocApplicationDetailSerializer
        return DocApplicationSerializerWithRelations

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        if not request.user.is_superuser:
            return self.error_response("You do not have permission to perform this action.", status.HTTP_403_FORBIDDEN)

        from core.services.bulk_delete import bulk_delete_applications

        query = (
            request.data.get("search_query") or request.data.get("searchQuery") or request.data.get("query") or ""
        ).strip()
        count = bulk_delete_applications(query=query or None)
        return Response({"deleted_count": count})

    @action(detail=True, methods=["post"], url_path="advance-workflow")
    def advance_workflow(self, request, pk=None):
        """Complete current workflow and create next step."""
        try:
            application = self.get_object()
        except DocApplication.DoesNotExist:
            return self.error_response("Application not found", status.HTTP_404_NOT_FOUND)

        # If product requires documents but none exist at all -> incomplete
        if application.product and (application.product.required_documents or "").strip():
            if not application.documents.filter(required=True).exists():
                return self.error_response("Document collection is not completed", status.HTTP_400_BAD_REQUEST)

        current_workflow = application.current_workflow
        if not current_workflow:
            return self.error_response("No current workflow found", status.HTTP_400_BAD_REQUEST)

        # Complete current workflow
        current_workflow.status = current_workflow.STATUS_COMPLETED
        current_workflow.updated_by = request.user
        current_workflow.save()

        # Create next workflow if exists
        next_task = application.next_task
        if next_task:
            from customer_applications.models.doc_workflow import DocWorkflow

            step = DocWorkflow(
                start_date=timezone.now().date(),
                task=next_task,
                doc_application=application,
                created_by=request.user,
                status=DocWorkflow.STATUS_PENDING,
            )
            step.due_date = step.calculate_workflow_due_date()
            step.save()

        # Refresh application status
        application.save()

        return Response({"success": True})

    @extend_schema(request=OpenApiTypes.OBJECT, responses=DocWorkflowSerializer)
    @action(detail=True, methods=["post"], url_path=r"workflows/(?P<workflow_id>[^/.]+)/status")
    def update_workflow_status(self, request, pk=None, workflow_id=None):
        """Update the status of a workflow step for an application."""
        from customer_applications.models.doc_workflow import DocWorkflow

        status_value = request.data.get("status")
        valid_statuses = {choice[0] for choice in DocWorkflow.STATUS_CHOICES}

        if not status_value or status_value not in valid_statuses:
            return self.error_response("Invalid workflow status", status.HTTP_400_BAD_REQUEST)

        workflow = (
            DocWorkflow.objects.select_related("doc_application").filter(pk=workflow_id, doc_application_id=pk).first()
        )
        if not workflow:
            return self.error_response("Workflow not found", status.HTTP_404_NOT_FOUND)

        if (
            status_value == DocWorkflow.STATUS_COMPLETED
            and not workflow.doc_application.is_document_collection_completed
        ):
            return self.error_response("Document collection is not completed", status.HTTP_400_BAD_REQUEST)

        workflow.status = status_value
        workflow.updated_by = request.user
        workflow.save()

        workflow.doc_application.updated_by = request.user
        workflow.doc_application.save()

        from api.serializers.doc_workflow_serializer import DocWorkflowSerializer

        return Response(DocWorkflowSerializer(workflow).data)

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
        - b64_resized_image: Base64 encoded preview (if img_preview=true)
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

        try:
            safe_filename = get_valid_filename(os.path.basename(file.name))
            tmp_file_path = os.path.join(getattr(settings, "TMPFILES_FOLDER", "tmpfiles"), safe_filename)
            file_path = default_storage.save(tmp_file_path, file)

            job = OCRJob.objects.create(
                status=OCRJob.STATUS_QUEUED,
                progress=0,
                file_path=file_path,
                file_url=default_storage.url(file_path),
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
                },
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception as e:
            errMsg = e.args[0] if e.args else str(e)
            return self.error_response(errMsg, status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path=r"status/(?P<job_id>[^/.]+)")
    def status(self, request, job_id=None):
        try:
            job = OCRJob.objects.get(id=job_id)
        except OCRJob.DoesNotExist:
            return self.error_response("OCR job not found", status.HTTP_404_NOT_FOUND)

        response_data = {
            "job_id": str(job.id),
            "status": job.status,
            "progress": job.progress,
        }

        if job.status == OCRJob.STATUS_COMPLETED:
            if job.result:
                response_data.update(job.result)
            if job.save_session and not job.session_saved and job.result:
                request.session["file_path"] = default_storage.path(job.file_path)
                request.session["file_url"] = job.file_url
                request.session["mrz_data"] = job.result.get("mrz_data")
                request.session.save()
                job.session_saved = True
                job.save(update_fields=["session_saved", "updated_at"])
        elif job.status == OCRJob.STATUS_FAILED:
            response_data["error"] = job.error_message or "OCR job failed"

        return Response(data=response_data, status=status.HTTP_200_OK)


class DocumentOCRViewSet(ApiErrorHandlingMixin, viewsets.ViewSet):
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
                },
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception as e:
            errMsg = e.args[0] if e.args else str(e)
            return self.error_response(errMsg, status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path=r"status/(?P<job_id>[^/.]+)")
    def status(self, request, job_id=None):
        try:
            job = DocumentOCRJob.objects.get(id=job_id)
        except DocumentOCRJob.DoesNotExist:
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
    """
    API endpoint for dashboard statistics.
    TO BE REMOVED WHEN ANGULAR FRONTEND IS COMPLETE
    """

    permission_classes = [IsAuthenticated]

    def list(self, request):
        stats = {
            "customers": Customer.objects.count(),
            "applications": DocApplication.objects.filter(
                status__in=[DocApplication.STATUS_PENDING, DocApplication.STATUS_PROCESSING]
            ).count(),
            "invoices": InvoiceApplication.objects.not_fully_paid().count(),
        }
        return Response(stats)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([ScopedRateThrottle])
def exec_cron_jobs(request):
    """
    Execute cron jobs via Huey
    """
    request.throttle_scope = "cron"
    run_full_backup_now.delay()
    run_clear_cache_now.delay()
    return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)


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
@permission_classes([IsAuthenticated])
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
