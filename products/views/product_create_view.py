from django.forms import formset_factory
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

        # Check if tasks formset and required_documents formset are valid
        if tasks.is_valid():
            with transaction.atomic():
                required_documents = form.cleaned_data['required_documents']
                if len(required_documents) == 0:
                    form.instance.required_documents = ''
                else:
                    required_documents_str = ''
                    for document in required_documents:
                        required_documents_str += document.name + ','
                    form.instance.required_documents = required_documents_str[:-1]

                self.object = form.save()
                tasks.instance = self.object
                # Save the tasks formset
                tasks.save()
                return super().form_valid(form)

        # If either formset is not valid, don't save anything
        return super().form_invalid(form)
