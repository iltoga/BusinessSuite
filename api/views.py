from rest_framework import status
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

class ProductRequiredDocumentsView(APIView):
    queryset = Product.objects.all()

    def get(self, request, *args, **kwargs):
        product_id = self.kwargs.get('product_id')
        if product_id:
            try:
                product = Product.objects.get(id=product_id)
                # split the string into a list and trim the spaces
                required_documents = product.required_documents.split(',')
                required_documents = [document.strip() for document in required_documents]
                return Response({'required_documents': required_documents})
            except Product.DoesNotExist:
                return Response({'error': 'Product does not exist'}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({'error': 'Invalid request'}, status=status.HTTP_400_BAD_REQUEST)

class ProductsByTypeView(APIView):

    def get(self, request, product_type):
        products = Product.objects.filter(product_type=product_type)
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)
