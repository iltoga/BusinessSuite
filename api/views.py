from rest_framework.response import Response
from rest_framework.decorators import api_view
from customers.models import Customer
from .serializers import CustomerSerializer  # make sure to import your new serializer

@api_view(['GET'])
def get_customers(request):
    customers = Customer.objects.all()
    serializer = CustomerSerializer(customers, many=True)  # serialize the data
    return Response(serializer.data)  # return serialized data
