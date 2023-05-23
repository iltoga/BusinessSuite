from django.urls import reverse_lazy
from django.views.generic.edit import CreateView
from customers.models import Customer
from customers.forms import CustomerForm
from django.core.exceptions import ValidationError

class CustomerCreateView(CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'customers/customer_form.html'
    success_url = reverse_lazy('list')

    def form_valid(self, form):
        try:
            form.cleaned_data
        except ValidationError as e:
            form.add_error(None, e)
            return super().form_invalid(form)
        else:
            return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = reverse_lazy('create')
        return context