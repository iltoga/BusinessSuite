from django import forms
from .models import Product, DocApplication


class DocApplicationForm(forms.ModelForm):
    class Meta:
        model = DocApplication
        fields = '__all__'

    class Media:
        js = ('js/doc_application_admin.js',)
