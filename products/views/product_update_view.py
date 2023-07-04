from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from products.forms import ProductForm, TaskModelFormSet
from products.models import Product, Task


class ProductUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ("products.change_product",)
    model = Product
    form_class = ProductForm
    template_name = "products/product_form.html"
    success_url = reverse_lazy("product-list")
    success_message = "Product updated successfully!"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["action_name"] = "Update"
        if self.request.POST:
            data["tasks"] = TaskModelFormSet(self.request.POST, instance=self.object, prefix="tasks")
        else:
            data["tasks"] = TaskModelFormSet(instance=self.object, prefix="tasks")
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        tasks_formset = context["tasks"]

        if tasks_formset.is_valid():
            with transaction.atomic():
                required_documents_multiselect = form.cleaned_data.get("required_documents_multiselect")
                if not required_documents_multiselect:
                    self.object.required_documents = ""
                else:
                    required_documents_str = ""
                    for document in required_documents_multiselect:
                        required_documents_str += document.name + ","
                    self.object.required_documents = required_documents_str[:-1]

                optional_documents_multiselect = form.cleaned_data.get("optional_documents_multiselect")
                if not optional_documents_multiselect:
                    self.object.optional_documents = ""
                else:
                    optional_documents_str = ""
                    for document in optional_documents_multiselect:
                        optional_documents_str += document.name + ","
                    self.object.optional_documents = optional_documents_str[:-1]

                self.object = form.save()

                for form in tasks_formset:
                    # check if form instance already exists in the db or it's a new instance
                    if form.instance.pk is None:
                        form.instance.product = self.object
                    form.save()
                return super().form_valid(form)

        return super().form_invalid(form)
