from django.views.generic.edit import UpdateView
from django.urls import reverse_lazy
from customers.forms import CustomerForm
from customers.models import Customer
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin

class CustomerUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ('customers.change_customer',)
    model = Customer
    form_class = CustomerForm
    template_name = 'customers/customer_form.html'
    success_url = reverse_lazy('customer-list')
    success_message = "Customer updated successfully!"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = reverse_lazy('customer-update', kwargs={'pk': self.object.pk})
        context['action_name'] = 'Update'
        return context