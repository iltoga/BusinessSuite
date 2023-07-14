import mimetypes
import os
from datetime import datetime
from math import e

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db.models import Count, Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import (
    CustomerSerializer,
    DocApplicationSerializerWithRelations,
    DocumentTypeSerializer,
    ProductSerializer,
)
from core.utils.dateutils import calculate_due_date
from core.utils.imgutils import convert_and_resize_image
from core.utils.passport_ocr import extract_mrz_data
from customer_applications.models import DocApplication
from customers.models import Customer
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
        serializer = CustomerSerializer(self.queryset, many=True)
        return Response(serializer.data)


class ProductsView(APIView):
    queryset = Product.objects.all()

    def get(self, request):
        serializer = ProductSerializer(self.queryset, many=True)
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
                tmp_file_path = os.path.join(settings.MEDIA_ROOT, settings.TMPFILES_FOLDER, file.name)
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
            errMsg = e.args[0]
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exec_cron_jobs(request):
    """
    Execute cron jobs via django_cron
    """
    # run all jobs
    call_command("runcrons")
    return Response({"status": "success"}, status=status.HTTP_200_OK)
