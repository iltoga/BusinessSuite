from django.views.generic.edit import UpdateView
from django.urls import reverse_lazy
from customers.forms import CustomerForm
from customers.models import Customer


class UpdateCustomerView(UpdateView):
    model = Customer
    template_name = 'customers/update_customer.html'
    form_class = CustomerForm
    success_url = reverse_lazy('list')

    def form_valid(self, form):
        # This method is called when valid form data has been POSTed.
        # It should return an HttpResponse.
        form.save()  # This will create the customer
        return super().form_valid(form)