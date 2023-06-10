from django.urls import reverse_lazy
from django.db import transaction
from products.models import Product
from products.forms import ProductForm, TaskModelFormSet
from django.views.generic import CreateView
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.mixins import PermissionRequiredMixin

class ProductCreateView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ('products.add_product',)
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'
    success_url = reverse_lazy('product-list')
    success_message = "Product created successfully!"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['action_name'] = "Create"
        if self.request.POST:
            data['tasks'] = TaskModelFormSet(self.request.POST, prefix='tasks')
        else:
            data['tasks'] = TaskModelFormSet(prefix='tasks')
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        tasks = context['tasks']

        if tasks.is_valid():  # Check if tasks formset is valid first
            with transaction.atomic():
                self.object = form.save()  # Save the main form only if tasks formset is valid
                tasks.instance = self.object
                tasks.save()  # Save the tasks formset
                return super().form_valid(form)

        return super().form_invalid(form)  # If tasks formset is not valid, don't save anything
