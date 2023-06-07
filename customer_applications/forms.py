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


class RequiredDocumentCreateForm(forms.ModelForm):
    class Meta:
        model = RequiredDocument
        fields = ['doc_type']


class RequiredDocumentUpdateForm(forms.ModelForm):
    ocr_check = forms.BooleanField(required=False, label='OCR Check (only for Passports)')
    # checkbox to force update even if there are errors. the field is hideen by default and shown only if there are errors
    force_update = forms.BooleanField(required=False, label='Force Update', widget=forms.HiddenInput())
    # Only users with the 'upload_document' permission can upload documents
    field_permissions = {
        'file': ['upload_document'],
        'ocr_check': ['upload_document'],
    }

    class Meta:
        model = RequiredDocument
        fields = ['doc_type', 'file', 'ocr_check', 'doc_number', 'expiration_date', 'force_update']
        widgets = {
            'expiration_date': forms.DateInput(attrs={'type': 'date'}),
            'metadata': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super(RequiredDocumentUpdateForm, self).__init__(*args, **kwargs)
        self.fields['doc_type'].disabled = True
        doc_type = self.instance.doc_type.lower()
        # Defaults ocr_check to True if the document is a passport and there is no file_link
        if doc_type == 'passport' and not self.instance.file_link:
            self.initial['ocr_check'] = True
        # if the document is already expired, show the force_update checkbox
        #TODO: if the check to show force_update in case of errors in validate method is not working, try with this one
        # if self.instance.expiration_date and self.instance.expiration_date < timezone.now().date():
        #     self.fields['force_update'].widget = forms.CheckboxInput()

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
        # if we are forcing update, we don't need to check for errors
        force_update = cleaned_data.get('force_update', False)
        if force_update:
            return cleaned_data
        # Check that the document is not expiring in less than prodcut.documents_min_validity days from this applicn's doc_date
        expiration_date = cleaned_data.get('expiration_date', False)
        if expiration_date:
            if expiration_date < timezone.now().date():
                raise self.add_error('expiration_date', "Expiration date must not be in the past.")
            doc_date = cleaned_data.get('doc_date', False)
            if doc_date:
                product = self.instance.doc_application.product
                if (expiration_date - doc_date).days < product.documents_min_validity:
                    self.add_error('expiration_date', "Document is expiring in less than %d days from the application date." % product.documents_min_validity)
        return cleaned_data

    def is_valid(self):
        valid = super(RequiredDocumentUpdateForm, self).is_valid()
        # if the form is not valid, show the force_update checkbox
        if not valid:
            self.fields['force_update'].widget = forms.CheckboxInput()
        return valid

class DocWorkflowForm(forms.ModelForm):
    class Meta:
        model = DocWorkflow
        # fields = ['status', 'comment']
        exclude = ['completion_date', 'user', 'created_at', 'created_by']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 5, 'class': 'col-md-12'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'value': timezone.now().strftime("%Y-%m-%d"), 'class': 'col-md-4'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'col-md-4'}),
            'status': forms.Select(attrs={'class': 'col-md-4'}),
            'doc_application': forms.HiddenInput(),
            'task': forms.HiddenInput(),
            'updated_by': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super(DocWorkflowForm, self).__init__(*args, **kwargs)
        self.doc_application = kwargs.pop('doc_application', None)

    def clean(self):
        cleaned_data = super().clean()

        start_date = cleaned_data.get('start_date')
        due_date = cleaned_data.get('due_date')
        completion_date = cleaned_data.get('completion_date')
        if self.doc_application:
            doc_date = self.instance.doc_application.doc_date
            if start_date and doc_date and start_date < doc_date:
                doc_date_fmt = doc_date.strftime("%d/%m/%Y")
                self.add_error('start_date', f"Start date must be after document's application date, which is {doc_date_fmt}.")

        if start_date and due_date and due_date < start_date:
            self.add_error('due_date', 'Due date must be after start date.')

        if completion_date and due_date and completion_date < due_date:
            self.add_error('completion_date', 'Completion date must be after due date.')

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


DocWorkflowCreateFormSet = forms.inlineformset_factory(
    DocApplication, # parent model
    DocWorkflow, # child model
    form=DocWorkflowForm, # form to use
    extra=0, # minimum number of forms to show
    max_num=10, # maximum number of forms to show
    can_delete=False, # enable deletion
)
