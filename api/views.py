from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import DjangoModelPermissions
from customers.models import Customer
from products.models import Product
from .serializers import CustomerSerializer, ProductSerializer
from django.db.models import Q


class SearchCustomers(APIView):
    queryset = Customer.objects.all()

    def get(self, request, format=None):
        query = request.GET.get('q', '')
        customers = self.queryset.filter(
            Q(full_name__icontains=query) |
            Q(document_id__icontains=query) |
            Q(email__icontains=query)
        )
        serializer = CustomerSerializer(customers, many=True)
        return Response(serializer.data)


class CustomersView(APIView):

    def get(self, request):
        customers = Customer.objects.all()
        serializer = CustomerSerializer(customers, many=True)
        return Response(serializer.data)


class ProductsView(APIView):

    def get(self, request):
        products = Product.objects.all()
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)


class RequiredDocumentsView(APIView):

    def get(self, request, product_id):
        product = Product.objects.get(id=product_id)
        required_documents = product.required_documents.split(',')
        return Response(required_documents)


class ProductsByTypeView(APIView):

    def get(self, request, product_type):
        products = Product.objects.filter(product_type=product_type)
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)
