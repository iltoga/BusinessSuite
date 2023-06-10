from django import forms
from products.models import Product

class ProductForm(forms.ModelForm):
    description = forms.CharField(widget=forms.Textarea(attrs={'rows': 1}))
    product_type = forms.ChoiceField(choices=Product.PRODUCT_TYPE_CHOICES, initial='visa')
    required_documents = forms.CharField(max_length=1024, widget=forms.TextInput(attrs={'data-role': 'tagsinput'}))
    validity = forms.IntegerField(label='Validity (days)', required=False)
    documents_min_validity = forms.IntegerField(label='Documents min. validity (days)', required=False)

    class Meta:
        model = Product
        fields = ['name', 'code', 'description', 'base_price', 'product_type', 'validity', 'required_documents', 'documents_min_validity']
