from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.forms import modelformset_factory
from sqlalchemy import Transaction
from .models import Product, Task
from .forms import ProductForm, TaskForm, TaskModelFormSet
from django.views.generic import ListView, DetailView, DeleteView, UpdateView, CreateView

class ProductCreateView(CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'
    success_url = reverse_lazy('products:product-list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['tasks'] = TaskModelFormSet(self.request.POST, prefix='tasks')
        else:
            data['tasks'] = TaskModelFormSet(prefix='tasks')
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        tasks = context['tasks']
        with Transaction.atomic():
            self.object = form.save()
            if tasks.is_valid():
                tasks.instance = self.object
                tasks.save()
        return super().form_valid(form)

class ProductUpdateView(View):
    def get(self, request, *args, **kwargs):
        product = Product.objects.get(pk=kwargs['pk'])
        product_form = ProductForm(prefix='product', instance=product)
        TaskFormSet = modelformset_factory(Task, form=TaskForm, extra=1)
        task_formset = TaskFormSet(prefix='tasks', queryset=product.tasks.all())
        return render(request, 'products/product_form.html', {'product_form': product_form, 'task_formset': task_formset})

    def post(self, request, *args, **kwargs):
        product = Product.objects.get(pk=kwargs['pk'])
        product_form = ProductForm(request.POST, prefix='product', instance=product)
        TaskFormSet = modelformset_factory(Task, form=TaskForm, extra=1)
        task_formset = TaskFormSet(request.POST, prefix='tasks', queryset=product.tasks.all())
        if product_form.is_valid() and task_formset.is_valid():
            product_form.save()
            tasks = task_formset.save
            for task in tasks:
                task.product = product
                task.save()
            return redirect('products:product-list')
        return render(request, 'products/product_form.html', {'product_form': product_form, 'task_formset': task_formset})

class ProductDeleteView(DeleteView):
    model = Product
    template_name = "products/product_confirm_delete.html"
    success_url = reverse_lazy('product_list')


class ProductListView(ListView):
    model = Product
    template_name = "products/product_list.html"
    paginate_by = 15

    def get_queryset(self):
        query = self.request.GET.get('q')
        if query:
            return Product.objects.filter(name__icontains=query)
        else:
            return Product.objects.all()


class ProductDetailView(DetailView):
    model = Product
    template_name = "yourapp/product_detail.html"
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tasks'] = Task.objects.filter(product=self.object)
        return context
