import mimetypes
import os
from datetime import datetime
from math import e

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db.models import Count, Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import (
    CustomerSerializer,
    DocApplicationSerializerWithRelations,
    DocumentTypeSerializer,
    ProductSerializer,
)
from core.models import CountryCode
from core.utils.dateutils import calculate_due_date
from core.utils.imgutils import convert_and_resize_image
from core.utils.passport_ocr import extract_mrz_data
from customer_applications.models import DocApplication
from customers.models import Customer
from invoices.models.invoice import InvoiceApplication
from products.models import Product
from products.models.document_type import DocumentType
from products.models.task import Task


class SearchCustomers(APIView):
    queryset = Customer.objects.all()

    def get(self, request, format=None):
        query = request.GET.get("q", "")
        customers = self.queryset.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
        )
        serializer = CustomerSerializer(customers, many=True)
        return Response(serializer.data)


class CustomersView(APIView):
    queryset = Customer.objects.all()

    def get(self, request):
        serializer = CustomerSerializer(self.queryset.all(), many=True)
        return Response(serializer.data)


class ProductsView(APIView):
    queryset = Product.objects.all()

    def get(self, request):
        serializer = ProductSerializer(self.queryset.all(), many=True)
        return Response(serializer.data)


class ProductByIDView(APIView):
    queryset = Product.objects.none()

    def get(self, request, *args, **kwargs):
        product_id = self.kwargs.get("product_id")
        if product_id:
            try:
                product = Product.objects.get(id=product_id)
                # split the string into a list and trim the spaces
                required_document_types_str = product.required_documents.split(",")
                required_document_types_str = [document.strip() for document in required_document_types_str]
                # get the corresponting DocumentType objects
                required_document_types = DocumentType.objects.filter(name__in=required_document_types_str)
                # serialize the product and the required documents
                serialized_product = ProductSerializer(product, many=False)
                serialzed_document_types = DocumentTypeSerializer(required_document_types, many=True)
                # also return the optional documents
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
            except Product.DoesNotExist:
                return Response({"error": "Product does not exist"}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({"error": "Invalid request"}, status=status.HTTP_400_BAD_REQUEST)


class CustomerApplicationsView(APIView):
    queryset = DocApplication.objects.none()

    def get(self, request, *args, **kwargs):
        """
        Returns all applications for a customer
        """
        customer_id = self.kwargs.get("customer_id")
        if customer_id:
            try:
                applications = DocApplication.objects.filter(customer_id=customer_id)

                # Get applications related to the customer and annotate them with the count of invoice_applications
                applications = applications.annotate(num_invoices=Count("invoice_applications"))

                # Filter applications based on provided kwargs. If not provided, use defaults
                # Defaults: exclude_incomplete_document_collection=True, status!=STATUS_REJECTED, num_invoices=0
                exclude_incomplete_document_collection = (
                    request.query_params.get("exclude_incomplete_document_collection", "true").lower() == "true"
                )
                exclude_statuses_string = request.query_params.get("exclude_statuses", None)
                if exclude_statuses_string:
                    exclude_statuses = [status for status in exclude_statuses_string.split(",")]
                    STATUS_DICT = dict(DocApplication.STATUS_CHOICES)
                    if not all(status in STATUS_DICT.keys() for status in exclude_statuses):
                        return Response(data={"error": "Invalid status provided"}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    exclude_statuses = [DocApplication.STATUS_REJECTED]
                exclude_with_invoices = request.query_params.get("exclude_with_invoices", "true").lower() == "true"

                if exclude_incomplete_document_collection:
                    applications = applications.filter_by_document_collection_completed()

                if exclude_statuses:
                    applications = applications.exclude(status__in=exclude_statuses)

                if exclude_with_invoices:
                    applications = applications.exclude(num_invoices__gt=0)

                serializer = DocApplicationSerializerWithRelations(applications, many=True)
                return Response(serializer.data)
            except Customer.DoesNotExist:
                return Response(data={"error": "Customer does not exist"}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response(data={"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data={"error": "Invalid request"}, status=status.HTTP_400_BAD_REQUEST)


class ProductsByTypeView(APIView):
    def get(self, request, product_type):
        products = Product.objects.filter(product_type=product_type)
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)


class OCRCheckView(APIView):
    def get_queryset(self):
        return Product.objects.none()

    def post(self, request):
        from django.utils.text import get_valid_filename

        file = request.data.get("file")
        if not file or file == "undefined":
            return Response(data={"error": "No file provided!"}, status=status.HTTP_400_BAD_REQUEST)

        valid_file_types = ["image/jpeg", "image/png", "image/tiff", "application/pdf"]
        file_type = mimetypes.guess_type(file.name)[0]
        if file_type not in valid_file_types:
            return Response(
                data={"error": "File format not supported. Only images (jpeg and png) and pdf are accepted!"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        doc_type = request.data.get("doc_type").lower()
        if not doc_type or doc_type == "undefined":
            return Response(data={"error": "No doc_type provided!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
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
            return Response(data={"b64_resized_image": img_str, "mrz_data": mrz_data}, status=status.HTTP_200_OK)
        except Exception as e:
            errMsg = e.args[0] if e.args else str(e)
            return Response(data={"error": errMsg}, status=status.HTTP_400_BAD_REQUEST)


# the urlpattern for this view is:
"""
    path(
        "compute/doc_workflow_due_date/int:<task_id>/date:start_date>/",
        views.ComputeDocworkflowDueDate.as_view(),
        name="api-compute-docworkflow-due-date",
    ),

"""


class ComputeDocworkflowDueDate(APIView):
    def get_queryset(self):
        return Product.objects.none()

    def get(self, request, *args, **kwargs):
        task_id = self.kwargs.get("task_id")
        start_date = self.kwargs.get("start_date")
        # check that the date is a valid date and convert it to a datetime object
        if start_date:
            try:
                start_date = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                return Response({"error": "Invalid date format. Date must be in the format YYYY-MM-DD"})
        if task_id:
            try:
                task = Task.objects.get(id=task_id)
                due_date = calculate_due_date(start_date, task.duration, task.duration_is_business_days)
                due_date = due_date.strftime("%Y-%m-%d")
                return Response({"due_date": due_date})
            except Task.DoesNotExist:
                return Response({"error": "Task does not exist"}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({"error": "Invalid request"}, status=status.HTTP_400_BAD_REQUEST)


class InvoiceApplicationDueAmountView(APIView):
    """
    Returns the due amount for an invoice application
    """

    queryset = InvoiceApplication.objects.none()

    def get(self, request, *args, **kwargs):
        invoice_application_id = self.kwargs.get("invoice_application_id")
        if invoice_application_id:
            try:
                invoice_application = InvoiceApplication.objects.get(pk=invoice_application_id)
                return Response(
                    {
                        "due_amount": str(invoice_application.due_amount),
                        "amount": str(invoice_application.amount),
                        "paid_amount": str(invoice_application.paid_amount),
                    }
                )
            except InvoiceApplication.DoesNotExist:
                return Response({"error": "Invoice Application does not exist"}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({"error": "Invalid request"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exec_cron_jobs(request):
    """
    Execute cron jobs via django_cron
    """
    # run all jobs
    call_command("runcrons")
    return Response({"status": "success"}, status=status.HTTP_200_OK)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def customer_quick_create(request):
    """
    Quick create a customer with minimal required fields
    """
    try:
        # Extract data from request
        data = {
            "title": request.data.get("title", ""),
            "customer_type": request.data.get("customer_type", "person"),
            "first_name": request.data.get("first_name"),
            "last_name": request.data.get("last_name"),
            "company_name": request.data.get("company_name", ""),
            "npwp": request.data.get("npwp", ""),
            "birthdate": request.data.get("birthdate"),
            "email": request.data.get("email", None),
            "telephone": request.data.get("telephone", None),
            "whatsapp": request.data.get("whatsapp", None),
            "address_bali": request.data.get("address_bali", ""),
            "address_abroad": request.data.get("address_abroad", ""),
            "passport_number": request.data.get("passport_number", ""),
            "passport_issue_date": request.data.get("passport_issue_date", None),
            "passport_expiration_date": request.data.get("passport_expiration_date", None),
            "gender": request.data.get("gender", ""),
        }

        # Handle nationality
        nationality_code = request.data.get("nationality")
        if nationality_code:
            try:
                nationality = CountryCode.objects.get(alpha3_code=nationality_code)
                data["nationality"] = nationality
            except CountryCode.DoesNotExist:
                pass

        # Validate required fields based on customer type
        customer_type = data.get("customer_type", "person")
        if customer_type == "person":
            if not data["first_name"] or not data["last_name"]:
                return Response(
                    {
                        "success": False,
                        "errors": {"__all__": ["First name and last name are required for person customers."]},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif customer_type == "company":
            if not data["company_name"]:
                return Response(
                    {"success": False, "errors": {"__all__": ["Company name is required for company customers."]}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Handle empty birthdate
        if not data["birthdate"]:
            data.pop("birthdate")

        # Create customer
        # parse passport dates if provided
        from datetime import datetime

        if data.get("passport_issue_date") and isinstance(data["passport_issue_date"], str):
            try:
                data["passport_issue_date"] = datetime.strptime(data["passport_issue_date"], "%Y-%m-%d").date()
            except ValueError:
                try:
                    data["passport_issue_date"] = datetime.strptime(data["passport_issue_date"], "%d/%m/%Y").date()
                except ValueError:
                    data["passport_issue_date"] = None
        if data.get("passport_expiration_date") and isinstance(data["passport_expiration_date"], str):
            try:
                data["passport_expiration_date"] = datetime.strptime(
                    data["passport_expiration_date"], "%Y-%m-%d"
                ).date()
            except ValueError:
                try:
                    data["passport_expiration_date"] = datetime.strptime(
                        data["passport_expiration_date"], "%d/%m/%Y"
                    ).date()
                except ValueError:
                    data["passport_expiration_date"] = None

        customer = Customer.objects.create(**data)

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
def customer_application_quick_create(request):
    """
    Quick create a customer application with documents and workflows
    """
    try:
        from core.utils.dateutils import calculate_due_date
        from customer_applications.models import Document, DocWorkflow
        from products.models.document_type import DocumentType

        # Extract data from request
        customer_id = request.data.get("customer")
        product_id = request.data.get("product")
        doc_date = request.data.get("doc_date")
        notes = request.data.get("notes", "")

        # Validate required fields
        if not customer_id or not product_id or not doc_date:
            return Response(
                {"success": False, "errors": {"__all__": ["Customer, product and application date are required."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse doc_date if it's a string
        from datetime import datetime

        if isinstance(doc_date, str):
            try:
                doc_date = datetime.strptime(doc_date, "%Y-%m-%d").date()
            except ValueError:
                try:
                    doc_date = datetime.strptime(doc_date, "%d/%m/%Y").date()
                except ValueError:
                    return Response(
                        {"success": False, "error": "Invalid date format. Use YYYY-MM-DD or DD/MM/YYYY."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # Get customer and product
        try:
            customer = Customer.objects.get(pk=customer_id)
            product = Product.objects.get(pk=product_id)
        except (Customer.DoesNotExist, Product.DoesNotExist) as e:
            return Response(
                {"success": False, "error": "Customer or product not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create DocApplication
        doc_app = DocApplication.objects.create(
            customer=customer,
            product=product,
            doc_date=doc_date,
            notes=notes,
            created_by=request.user,
        )

        # Create documents based on product requirements
        required_docs_str = product.required_documents or ""
        optional_docs_str = product.optional_documents or ""

        required_doc_names = [name.strip() for name in required_docs_str.split(",") if name.strip()]
        optional_doc_names = [name.strip() for name in optional_docs_str.split(",") if name.strip()]

        # Create required documents
        for doc_name in required_doc_names:
            try:
                doc_type = DocumentType.objects.get(name=doc_name)
                Document.objects.create(
                    doc_application=doc_app,
                    doc_type=doc_type,
                    required=True,
                    created_by=request.user,
                )
            except DocumentType.DoesNotExist:
                pass

        # Create optional documents
        for doc_name in optional_doc_names:
            try:
                doc_type = DocumentType.objects.get(name=doc_name)
                Document.objects.create(
                    doc_application=doc_app,
                    doc_type=doc_type,
                    required=False,
                    created_by=request.user,
                )
            except DocumentType.DoesNotExist:
                pass

        # Create initial workflow step
        first_task = product.tasks.order_by("step").first()
        if first_task:
            due_date = calculate_due_date(
                start_date=doc_app.doc_date,
                days_to_complete=first_task.duration,
                business_days_only=first_task.duration_is_business_days,
            )
            DocWorkflow.objects.create(
                doc_application=doc_app,
                task=first_task,
                start_date=timezone.now().date(),  # REQUIRED: start_date must be set
                due_date=due_date,
                status=DocWorkflow.STATUS_PENDING,
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


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def product_quick_create(request):
    """
    Quick create a product with minimal required fields
    """
    try:
        # Extract and clean data from request
        validity = request.data.get("validity")
        documents_min_validity = request.data.get("documents_min_validity")
        base_price = request.data.get("base_price")

        # Convert empty strings to None for integer fields
        if validity == "" or validity is None:
            validity = None
        if documents_min_validity == "" or documents_min_validity is None:
            documents_min_validity = None
        if base_price == "" or base_price is None:
            base_price = 0.00

        data = {
            "name": request.data.get("name"),
            "code": request.data.get("code"),
            "product_type": request.data.get("product_type", "other"),
            "description": request.data.get("description", ""),
            "base_price": base_price,
            "validity": validity,
            "documents_min_validity": documents_min_validity,
            "required_documents": request.data.get("required_documents", ""),
            "optional_documents": request.data.get("optional_documents", ""),
        }

        # Validate required fields
        if not data["name"] or not data["code"] or not data["product_type"]:
            return Response(
                {"success": False, "errors": {"__all__": ["Name, code and product type are required."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if code already exists
        if Product.objects.filter(code=data["code"]).exists():
            return Response(
                {"success": False, "errors": {"code": ["A product with this code already exists."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create product
        product = Product.objects.create(**data)

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
