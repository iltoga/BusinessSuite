from django import forms
from django.forms import Select, formset_factory
from products.models import Product
from products.models import DocumentType

class ProductForm(forms.ModelForm):
    description = forms.CharField(widget=forms.Textarea(attrs={'rows': 1}))
    product_type = forms.ChoiceField(
        choices=Product.PRODUCT_TYPE_CHOICES,
        initial='visa')
    validity = forms.IntegerField(label='Validity (days)', required=False)
    documents_min_validity = forms.IntegerField(
        label='Documents min. validity (days)',
        required=False)

    # Extra form fields
    required_documents_multiselect = forms.ModelMultipleChoiceField(
        queryset=DocumentType.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'select2'}),
        required=False,
        label='Required documents',)

    class Meta:
        model = Product
        fields = ['name', 'code', 'description', 'base_price', 'product_type',
                  'validity', 'documents_min_validity']

    def __init__(self, *args, **kwargs):
        super(ProductForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs and kwargs['instance']:
            document_names = kwargs['instance'].required_documents.split(',')
            document_objects = DocumentType.objects.filter(name__in=document_names)
            self.fields['required_documents_multiselect'].initial = document_objects
