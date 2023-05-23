from django.views.generic.edit import UpdateView
from django.urls import reverse_lazy
from customers.forms import CustomerForm
from customers.models import Customer
from django.core.exceptions import ValidationError

class CustomerUpdateView(UpdateView):
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
        context['action'] = reverse_lazy('update', kwargs={'pk': self.object.pk})
        return context