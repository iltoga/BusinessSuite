from customer_applications.models import DocApplication
from django import forms
from django.utils import timezone

from customers.models import Customer
from products.models import Product

class DocApplicationForm(forms.ModelForm):
    class Meta:
        model = DocApplication
        fields = ['application_type', 'customer', 'product', 'doc_date', 'price']
        widgets = {
            'doc_date': forms.DateInput(attrs={'type': 'date', 'value': timezone.now().strftime("%Y-%m-%d")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:  # if instance exists and has a primary key
            self.fields['customer'].disabled = True
            self.fields['product'].disabled = True
            self.fields['application_type'].disabled = True
        else:  # Creating new record
            self.fields['customer'].widget = forms.Select(attrs={'class': 'select2'})
            self.fields['product'].widget = forms.Select(attrs={'class': 'select2'})
            self.fields['customer'].queryset = Customer.objects.all()
            self.fields['product'].queryset = Product.objects.all()
