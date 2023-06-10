from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import UpdateView
from products.forms import ProductForm, TaskModelFormSet
from products.models import Product
from django.db import transaction

class ProductUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ('products.change_product',)
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'
    success_url = reverse_lazy('product-list')
    success_message = "Product updated successfully!"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['action_name'] = "Update"
        if self.request.POST:
            data['tasks'] = TaskModelFormSet(self.request.POST, instance=self.object, prefix='tasks')
        else:
            data['tasks'] = TaskModelFormSet(instance=self.object, prefix='tasks')
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        tasks = context['tasks']
        with transaction.atomic():
            self.object = form.save(commit=False)  # Don't save the form to the database yet
            if tasks.is_valid():
                tasks.instance = self.object
                tasks.save()  # Save the tasks to the database
                self.object.save()  # Now save the form to the database
                return super().form_valid(form)

            return super().form_invalid(form)  # If tasks aren't valid, don't save anything
