from django.http import JsonResponse
from django.views import View
from django.core import serializers
from customers.models import Customer
from django.db.models import Q

class CustomerSearchApiView(View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '')
        # if len(query) >= 2:
        customers = Customer.objects.filter(
            Q(full_name__icontains=query) |
            Q(document_id__icontains=query) |
            Q(email__icontains=query)
        )
        customer_data = serializers.serialize('json', customers)
        return JsonResponse(customer_data, safe=False)
        # else:
        #     return JsonResponse([], safe=False)
