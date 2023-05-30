from django.views.generic import ListView
from customers.models import Customer
from django.contrib.auth.mixins import PermissionRequiredMixin

class CustomerListView(PermissionRequiredMixin, ListView):
    permission_required = ('customers.view_customer',)
    model = Customer
    paginate_by = 15  # Change this number to the desired items per page
    template_name = 'customers/customer_list.html'  # Assuming your template is in this location

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get('q')
        if query:
            queryset = self.model.objects.search_customers(query)
        return queryset
