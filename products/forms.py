from typing import Any, Dict
from django import forms
from django.db import transaction
from .models import Product, Task

class ProductForm(forms.ModelForm):
    description = forms.CharField(widget=forms.Textarea(attrs={'rows': 1}))
    product_type = forms.ChoiceField(choices=Product.PRODUCT_TYPE_CHOICES, initial='visa')
    required_documents = forms.CharField(max_length=1024, widget=forms.TextInput(attrs={'data-role': 'tagsinput'}))
    validity = forms.IntegerField(label='Validity (days)', required=False)
    documents_min_validity = forms.IntegerField(label='Documents min. validity (days)', required=False)

    class Meta:
        model = Product
        fields = ['name', 'code', 'description', 'base_price', 'product_type', 'validity', 'required_documents', 'documents_min_validity']

class TaskForm(forms.ModelForm):
    description = forms.CharField(widget=forms.Textarea(attrs={'rows': 1}), required=False)

    class Meta:
        model = Task
        fields = ['product', 'step', 'last_step', 'name', 'description', 'cost', 'duration', 'duration_is_business_days', 'notify_days_before']

    # if update a new task, then the product field is disabled
    def __init__(self, *args, **kwargs):
        super(TaskForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['product'].disabled = True
            self.fields['step'].disabled = True

TaskModelFormSet = forms.inlineformset_factory(
    Product, # parent model
    Task, # child model
    form=TaskForm, # form to use
    extra=0, # minimum number of forms to show
    max_num=10, # maximum number of forms to show
    can_delete=False, # enable deletion
)