import mimetypes
import os
from datetime import datetime
from math import e

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import filters, pagination, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from api.serializers import (
    CustomerApplicationQuickCreateSerializer,
    CustomerQuickCreateSerializer,
    CustomerSerializer,
    DocApplicationSerializerWithRelations,
    DocumentTypeSerializer,
    ProductQuickCreateSerializer,
    ProductSerializer,
)
from core.services.quick_create import create_quick_customer, create_quick_customer_application, create_quick_product
from core.utils.dateutils import calculate_due_date
from core.utils.imgutils import convert_and_resize_image
from core.utils.passport_ocr import extract_mrz_data, extract_passport_with_ai
from customer_applications.models import DocApplication
from customers.models import Customer
from invoices.models.invoice import InvoiceApplication
from products.models import Product
from products.models.document_type import DocumentType
from products.models.task import Task


class ApiErrorHandlingMixin:
    def error_response(self, message, status_code=status.HTTP_400_BAD_REQUEST, details=None):
        payload = {"error": message}
        if details is not None:
            payload["details"] = details
        return Response(payload, status=status_code)

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        if response is None:
            return self.error_response("Server error", status.HTTP_500_INTERNAL_SERVER_ERROR)
        if isinstance(exc, ValidationError):
            return self.error_response("Validation error", response.status_code, details=response.data)
        if isinstance(exc, NotFound):
            return self.error_response("Not found", response.status_code)
        if isinstance(response.data, dict) and "detail" in response.data:
            return self.error_response(response.data["detail"], response.status_code)
        return response


class StandardResultsSetPagination(pagination.PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class CustomerViewSet(ApiErrorHandlingMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Customer.objects.select_related("nationality").all()

    serializer_class = CustomerSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["first_name", "last_name", "email", "company_name", "passport_number"]
    ordering_fields = ["first_name", "last_name", "email", "company_name", "passport_number"]
    ordering = ["last_name", "first_name"]

    def retrieve(self, request, *args, **kwargs):
        language = request.GET.get("document_lang", settings.DEFAULT_DOCUMENT_LANGUAGE_CODE)
        try:
            customer = Customer.objects.select_related("nationality").get(pk=kwargs.get("pk"))
        except Customer.DoesNotExist:
            return self.error_response("Customer not found", status.HTTP_404_NOT_FOUND)
        data = {
            "id": customer.id,
            "first_name": customer.first_name or "",
            "last_name": customer.last_name or "",
            "company_name": customer.company_name or "",
            "full_name": customer.full_name,
            "gender_display": customer.get_gender_display(language) if customer.gender else "",
            "nationality_name": (
                (
                    customer.nationality.country_idn
                    if getattr(customer.nationality, "country_idn", None)
                    else customer.nationality.country
                )
                if customer.nationality
                else ""
            ),
            "nationality_code": customer.nationality.alpha3_code if customer.nationality else "",
            "birth_place": customer.birth_place or "",
            "birthdate": customer.birthdate.isoformat() if customer.birthdate else "",
            "passport_number": customer.passport_number or "",
            "passport_expiration_date": (
                customer.passport_expiration_date.isoformat() if customer.passport_expiration_date else ""
            ),
            "address_bali": customer.address_bali or "",
        }
        return Response(data)

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


class ProductViewSet(ApiErrorHandlingMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "code", "product_type"]
    ordering_fields = ["name", "code", "product_type"]
    ordering = ["name"]

    def get_queryset(self):
        queryset = super().get_queryset()
        product_type = self.request.query_params.get("product_type")
        if product_type:
            queryset = queryset.filter(product_type=product_type)
        return queryset

    @action(detail=False, methods=["get"], url_path="get_product_by_id/(?P<product_id>[^/.]+)")
    def get_product_by_id(self, request, product_id=None):
        if not product_id:
            return self.error_response("Invalid request", status.HTTP_400_BAD_REQUEST)
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return self.error_response("Product does not exist", status.HTTP_404_NOT_FOUND)
        required_document_types_str = product.required_documents.split(",")
        required_document_types_str = [document.strip() for document in required_document_types_str]
        required_document_types = DocumentType.objects.filter(name__in=required_document_types_str)
        serialized_product = ProductSerializer(product, many=False)
        serialzed_document_types = DocumentTypeSerializer(required_document_types, many=True)
        optional_document_types_str = product.optional_documents.split(",")
        optional_document_types_str = [document.strip() for document in optional_document_types_str]
        optional_document_types = DocumentType.objects.filter(name__in=optional_document_types_str)
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


class InvoiceViewSet(ApiErrorHandlingMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

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

        if exclude_incomplete_document_collection:
            applications = applications.filter_by_document_collection_completed()

        if exclude_statuses:
            applications = applications.exclude(status__in=exclude_statuses)

        if exclude_with_invoices:
            applications = applications.exclude(num_invoices__gt=0)

        page = self.paginate_queryset(applications)
        if page is not None:
            serializer = DocApplicationSerializerWithRelations(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = DocApplicationSerializerWithRelations(applications, many=True)
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

        doc_type = request.data.get("doc_type").lower()
        if not doc_type or doc_type == "undefined":
            return self.error_response("No doc_type provided!", status.HTTP_400_BAD_REQUEST)

        # Check if AI extraction is requested
        use_ai = request.data.get("use_ai", "false").lower() == "true"

        try:
            # Use hybrid extraction if AI is enabled, otherwise use MRZ only
            if use_ai:
                mrz_data = extract_passport_with_ai(file, use_ai=True)
            else:
                mrz_data = extract_mrz_data(file)

            save_session = request.data.get("save_session")
            if save_session:
                # Sanitize filename to prevent path traversal and use RELATIVE path for storage
                safe_filename = get_valid_filename(os.path.basename(file.name))
                tmp_file_path = os.path.join(settings.TMPFILES_FOLDER, safe_filename)
                file_path = default_storage.save(tmp_file_path, file)
                request.session["file_path"] = default_storage.path(file_path)
                request.session["file_url"] = default_storage.url(file_path)
                request.session["mrz_data"] = mrz_data
                request.session.save()

            # Convert and resize the image. the file is the file path, not the file itself
            img_preview = request.data.get("img_preview", False)
            if img_preview:
                img_preview = True
            resize = request.data.get("resize", False)
            if resize:
                resize = True
            width = request.data.get("width", None)
            if width:
                width = int(width)
            _, img_str = convert_and_resize_image(
                file,
                file_type,
                return_encoded=img_preview,
                resize=resize,
                base_width=width,
            )

            # Build response with optional AI error warning
            response_data = {"b64_resized_image": img_str, "mrz_data": mrz_data}
            if "ai_error" in mrz_data:
                response_data["ai_warning"] = mrz_data.pop("ai_error")

            return Response(data=response_data, status=status.HTTP_200_OK)
        except Exception as e:
            errMsg = e.args[0] if e.args else str(e)
            return self.error_response(errMsg, status.HTTP_400_BAD_REQUEST)


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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def exec_cron_jobs(request):
    """
    Execute cron jobs via django_cron
    """
    request.throttle_scope = "cron"
    # run all jobs
    call_command("runcrons")
    return Response({"status": "success"}, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
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
@authentication_classes([SessionAuthentication])
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
        import traceback

        error_msg = str(e)
        print(f"Error in customer_application_quick_create: {error_msg}")
        print(traceback.format_exc())

        if hasattr(e, "message_dict"):
            # Django ValidationError
            return Response({"success": False, "errors": e.message_dict}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"success": False, "error": error_msg}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
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

        product = create_quick_product(validated_data=serializer.validated_data)

        return Response(
            {
                "success": True,
                "product": {
                    "id": product.id,
                    "name": product.name,
                    "code": product.code,
                    "product_type": product.product_type,
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
