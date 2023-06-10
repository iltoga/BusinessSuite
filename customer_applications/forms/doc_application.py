from customer_applications.models import DocApplication
from django import forms
from django.utils import timezone

class DocApplicationFormCreate(forms.ModelForm):
    class Meta:
        model = DocApplication
        fields = ['application_type', 'customer', 'product', 'doc_date', 'price']
        widgets = {
            'doc_date': forms.DateInput(attrs={'type': 'date', 'value': timezone.now().strftime("%Y-%m-%d")}),
            'product': forms.Select(attrs={'class': 'select2'}),
            'customer': forms.Select(attrs={'class': 'select2'}),
        }

class DocApplicationFormUpdate(forms.ModelForm):

    class Meta:
        model = DocApplication
        fields = ['application_type', 'customer', 'product', 'doc_date', 'price']
        widgets = {
            'doc_date': forms.DateInput(attrs={'type': 'date', 'value': timezone.now().strftime("%Y-%m-%d")}),
        }

    def __init__(self, *args, **kwargs):
        super(DocApplicationFormUpdate, self).__init__(*args, **kwargs)
        self.fields['customer'].disabled = True
        self.fields['product'].disabled = True
        self.fields['application_type'].disabled = True

