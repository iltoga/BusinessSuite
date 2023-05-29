from django.urls import reverse_lazy
from django.views.generic import DeleteView
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from customers.models import Customer

class CustomerDeleteView(PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    permission_required = ('customers.delete_customer',)
    model = Customer
    template_name = 'customers/customer_confirm_delete.html'
    success_url = reverse_lazy('customer-list')
    success_message = "Customer deleted successfully!"
