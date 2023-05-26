from rest_framework.response import Response
from rest_framework.decorators import api_view
from customers.models import Customer
from products.models import Product
from .serializers import CustomerSerializer, ProductSerializer

@api_view(['GET'])
def get_customers(request):
    customers = Customer.objects.all()
    serializer = CustomerSerializer(customers, many=True)  # serialize the data
    return Response(serializer.data)  # return serialized data

@api_view(['GET'])
def get_products(request):
    products = Product.objects.all()
    serializer = ProductSerializer(products, many=True)

@api_view(['GET'])
def get_required_documents(request, product_id):
    """
    return a list of product.required_documents (required documents contains a comma separated list of document names) from a product id
    """
    product = Product.objects.get(id=product_id)
    required_documents = product.required_documents.split(',')
    return Response(required_documents)

@api_view(['GET'])
def get_products_by_product_type(request, product_type):
    products = Product.objects.filter(product_type=product_type)
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


