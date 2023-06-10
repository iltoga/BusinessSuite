from customer_applications.models import RequiredDocument
from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from core.utils.ocr import extract_mrz_data

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
