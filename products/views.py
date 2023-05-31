from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.forms import modelformset_factory
from django.db import transaction
from .models import Product, Task
from .forms import ProductForm, TaskForm, TaskModelFormSet
from django.views.generic import ListView, DetailView, DeleteView, UpdateView, CreateView
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.mixins import PermissionRequiredMixin
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

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
        with transaction.atomic():
            self.object = form.save()  # Save the instance first
            if tasks.is_valid():
                tasks.instance = self.object
                tasks.save()
            else:
                return super().form_invalid(form)
        return super().form_valid(form)

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
            self.object = form.save()
            if tasks.is_valid():
                tasks.instance = self.object
                tasks.save()
            else:
                return super().form_invalid(form)
        return super().form_valid(form)

# a view to update a task
class TaskUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ('products.change_task',)
    model = Task
    form_class = TaskForm
    template_name = 'products/task_update.html'
    success_message = "Task updated successfully!"

    def get_success_url(self):
        return reverse_lazy('product-detail', kwargs={'pk': self.object.product.pk})


class ProductDeleteView(PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    permission_required = ('products.delete_product',)
    model = Product
    template_name = "products/product_confirm_delete.html"
    success_url = reverse_lazy('product-list')
    success_message = "Product deleted successfully!"


class ProductListView(PermissionRequiredMixin, ListView):
    permission_required = ('products.view_product',)
    model = Product
    context_object_name = 'products'  # Default is object_list if not specified
    template_name = "products/product_list.html"
    paginate_by = 15

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get('q')
        if query:
            queryset = self.model.objects.search_products(query)
        return queryset

class ProductDetailView(PermissionRequiredMixin, DetailView):
    permission_required = ('products.view_product',)
    model = Product
    template_name = "products/product_detail.html"
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tasks'] = Task.objects.filter(product=self.object)
        return context
