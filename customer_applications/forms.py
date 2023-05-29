from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import DocApplication, RequiredDocument, DocWorkflow

class DocApplicationForm(forms.ModelForm):
    class Meta:
        model = DocApplication
        fields = ['application_type', 'customer', 'product', 'doc_date', 'price']
        widgets = {
            'doc_date': forms.DateInput(attrs={'type': 'date', 'value': timezone.now().strftime("%Y-%m-%d")}),
            'product': forms.Select(attrs={'class': 'select2'}),
            'customer': forms.Select(attrs={'class': 'select2'}),
        }


class RequiredDocumentCreateForm(forms.ModelForm):
    class Meta:
        model = RequiredDocument
        fields = ['doc_type']


class RequiredDocumentUpdateForm(forms.ModelForm):
    completed = forms.BooleanField(required=False, disabled=True)
    doc_type = forms.CharField(required=False, disabled=True)
    # Only users with the 'upload_document' permission can upload documents
    field_permissions = {
        'file': ['upload_document'],
    }

    class Meta:
        model = RequiredDocument
        fields = ['doc_type', 'file', 'doc_number', 'expiration_date']
        widgets = {
            'expiration_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_file(self):
        file = self.cleaned_data.get('file', False)
        if file:
            if file.size > 10 * 1024 * 1024:  # file size limit: 10MB
                raise ValidationError("File size must not exceed 10MB.")
            if not file.content_type in ["application/pdf", "image/jpeg", "image/png"]:
                raise ValidationError("Only PDF, JPEG and PNG formats are accepted.")
        return file

    def clean_expiration_date(self):
        expiration_date = self.cleaned_data.get('expiration_date', False)
        if expiration_date:
            if expiration_date < timezone.now().date():
                raise ValidationError("Expiration date must not be in the past.")
        return expiration_date


RequiredDocumentCreateFormSet = forms.inlineformset_factory(
    DocApplication, # parent model
    RequiredDocument, # child model
    form=RequiredDocumentCreateForm, # form to use
    extra=0, # minimum number of forms to show
    max_num=20, # maximum number of forms to show
    can_delete=False, # enable deletion
)


RequiredDocumentUpdateFormSet = forms.inlineformset_factory(
    DocApplication, # parent model
    RequiredDocument, # child model
    form=RequiredDocumentUpdateForm, # form to use
    extra=0, # minimum number of forms to show
    max_num=20, # maximum number of forms to show
    can_delete=False, # enable deletion
)


# DocWorkflowFormSet = forms.inlineformset_factory(
#     DocApplication, # parent model
#     DocWorkflow, # child model
#     form=DocWorkflowForm, # form to use
#     extra=0, # minimum number of forms to show
#     max_num=10, # maximum number of forms to show
#     can_delete=False, # enable deletion
# )
