from django import forms
from .models import Product, Task

class ProductForm(forms.ModelForm):
    description = forms.CharField(widget=forms.Textarea(attrs={'rows': 1}))
    product_type = forms.ChoiceField(choices=Product.PRODUCT_TYPE_CHOICES, initial='visa')
    required_documents = forms.CharField(max_length=1024, widget=forms.TextInput(attrs={'data-role': 'tagsinput'}))

    class Meta:
        model = Product
        fields = ['name', 'code', 'description', 'base_price', 'product_type', 'validity', 'required_documents']

class TaskForm(forms.ModelForm):
    description = forms.CharField(widget=forms.Textarea(attrs={'rows': 1}))

    class Meta:
        model = Task
        fields = ['step', 'last_step', 'name', 'description', 'cost', 'duration']

TaskModelFormSet = forms.inlineformset_factory(
    Product, # parent model
    Task, # child model
    form=TaskForm, # form to use
    extra=1, # minimum number of forms to show
    max_num=10, # maximum number of forms to show
    can_delete=False, # enable deletion
)