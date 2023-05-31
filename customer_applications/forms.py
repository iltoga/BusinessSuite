import pprint
from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError

from core.utils.ocr import extract_mrz_data
from .models import DocApplication, RequiredDocument, DocWorkflow

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
    def __init__(self, *args, **kwargs):
        super(DocApplicationFormUpdate, self).__init__(*args, **kwargs)
        self.fields['customer'].disabled = True
        self.fields['product'].disabled = True
        self.fields['application_type'].disabled = True

    class Meta:
        model = DocApplication
        fields = ['application_type', 'customer', 'product', 'doc_date', 'price']
        widgets = {
            'doc_date': forms.DateInput(attrs={'type': 'date', 'value': timezone.now().strftime("%Y-%m-%d")}),
        }


class RequiredDocumentCreateForm(forms.ModelForm):
    class Meta:
        model = RequiredDocument
        fields = ['doc_type']


class RequiredDocumentUpdateForm(forms.ModelForm):
    ocr_check = forms.BooleanField(required=False, label='OCR Check (only for Passports)')

    def __init__(self, *args, **kwargs):
        super(RequiredDocumentUpdateForm, self).__init__(*args, **kwargs)
        self.fields['doc_type'].disabled = True

    # Only users with the 'upload_document' permission can upload documents
    field_permissions = {
        'file': ['upload_document'],
        'ocr_check': ['upload_document'],
    }

    class Meta:
        model = RequiredDocument
        fields = ['doc_type', 'file', 'ocr_check', 'doc_number', 'expiration_date']
        widgets = {
            'expiration_date': forms.DateInput(attrs={'type': 'date'}),
            'metadata': forms.Textarea(attrs={'rows': 5}),
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

    def clean(self):
        # Perform OCR if the user has checked the OCR checkbox
        cleaned_data = super().clean()
        ocr_check = cleaned_data.get("ocr_check", False)
        file = cleaned_data.get("file", False)
        if ocr_check and not file:
            raise ValidationError("You must upload a file to perform OCR.")

        if file and ocr_check:
            try:
                doc_metadata, mrz_data = extract_mrz_data(file)
                cleaned_data['metadata'] = doc_metadata
                cleaned_data['doc_number'] = mrz_data.get('document_number', False)
                cleaned_data['expiration_date'] = mrz_data.get('expiration_date', False)
            except Exception as e:
                self.add_error('file', str(e))
        # Check that the document is not expiring in less than prodcut.documents_min_validity days from this applicn's doc_date
        expiration_date = cleaned_data.get('expiration_date', False)
        if expiration_date:
            if expiration_date < timezone.now().date():
                raise ValidationError("Expiration date must not be in the past.")
            doc_date = cleaned_data.get('doc_date', False)
            if doc_date:
                product = self.instance.doc_application.product
                if (expiration_date - doc_date).days < product.documents_min_validity:
                    self.add_error('expiration_date', "Document is expiring in less than %d days from the application date." % product.documents_min_validity)

        return cleaned_data


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
