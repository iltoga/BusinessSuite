import mimetypes
from datetime import datetime

from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers.document_type_serializer import DocumentTypeSerializer
from core.utils.dateutils import calculate_due_date
from core.utils.passport_ocr import extract_mrz_data
from customers.models import Customer
from products.models import Product
from products.models.document_type import DocumentType
from products.models.task import Task

from .serializers import CustomerSerializer, ProductSerializer


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
        customers = Customer.objects.all()
        serializer = CustomerSerializer(customers, many=True)
        return Response(serializer.data)


class ProductsView(APIView):
    queryset = Product.objects.all()

    def get(self, request):
        products = Product.objects.all()
        serializer = ProductSerializer(products, many=True)
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
                return Response(
                    {"product": serialized_product.data, "required_documents": serialzed_document_types.data}
                )
            except Product.DoesNotExist:
                return Response({"error": "Product does not exist"}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({"error": "Invalid request"}, status=status.HTTP_400_BAD_REQUEST)


class ProductsByTypeView(APIView):
    def get(self, request, product_type):
        products = Product.objects.filter(product_type=product_type)
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)


class OCRCheckView(APIView):
    queryset = Product.objects.none()

    # This is a multipart/form-data request
    def post(self, request):
        file = request.data.get("file")
        if not file or file == "undefined":
            return Response(data={"error": "No file provided!"}, status=status.HTTP_400_BAD_REQUEST)
        # check if file is a valid format
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
        res = Response()
        try:
            mrz_data = extract_mrz_data(file)
            return Response(data=mrz_data, status=status.HTTP_200_OK)
        except Exception as e:
            errMsg = e.args[0]
            # the one below always returns a error message of "Bad Request". I want to return the actual error message
            return Response(data={"error": errMsg}, status=status.HTTP_400_BAD_REQUEST)
        return res


# the urlpattern for this view is:
"""
    path(
        "compute/doc_workflow_due_date/int:<task_id>/date:start_date>/",
        views.ComputeDocworkflowDueDate.as_view(),
        name="api-compute-docworkflow-due-date",
    ),

"""


class ComputeDocworkflowDueDate(APIView):
    queryset = Task.objects.none()

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
