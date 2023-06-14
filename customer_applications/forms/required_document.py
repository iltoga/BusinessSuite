import mimetypes

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from customer_applications.models import RequiredDocument
from products.models import DocumentType


class RequiredDocumentCreateForm(forms.ModelForm):
    class Meta:
        model = RequiredDocument
        fields = ["doc_type"]


class RequiredDocumentUpdateForm(forms.ModelForm):
    # ocr_check = forms.BooleanField(required=False, label="OCR Check (only for Passports)")
    # checkbox to force update even if there are errors. the field is hideen by default and shown only if there are errors
    force_update = forms.BooleanField(required=False, label="Force Update", widget=forms.HiddenInput())
    # Only users with the 'upload_document' permission can upload documents
    field_permissions = {
        "file": ["upload_document"],
        "ocr_check": ["upload_document"],
    }

    class Meta:
        model = RequiredDocument
        fields = [
            "doc_type",
            "file",
            "ocr_check",
            "doc_number",
            "expiration_date",
            "details",
            "force_update",
            "completed",
            "metadata",
        ]
        widgets = {
            "expiration_date": forms.DateInput(attrs={"type": "date"}),
            "metadata": forms.HiddenInput(),
            "completed": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super(RequiredDocumentUpdateForm, self).__init__(*args, **kwargs)
        self.fields["doc_type"].widget = forms.HiddenInput()
        self.fields["ocr_check"].widget = forms.HiddenInput()
        form_doc_type = self.instance.doc_type

        # Set form fields visibility based on the document type
        self.product_doc_type = DocumentType.objects.get(name=form_doc_type)
        if not self.product_doc_type:
            raise ValidationError("Document type not found.")
        if not self.product_doc_type.has_ocr_check:
            self.fields["ocr_check"].widget = forms.HiddenInput()
        elif not self.instance.file_link:
            self.initial["ocr_check"] = True

        if not self.product_doc_type.has_expiration_date:
            self.fields["expiration_date"].widget = forms.HiddenInput()
        if not self.product_doc_type.has_doc_number:
            self.fields["doc_number"].widget = forms.HiddenInput()
        if not self.product_doc_type.has_file:
            self.fields["file"].widget = forms.HiddenInput()
        if not self.product_doc_type.has_details:
            self.fields["details"].widget = forms.HiddenInput()
        if self.product_doc_type.has_file and not self.product_doc_type.has_details:
            self.fields["file"].required = True
        elif self.product_doc_type.has_details and not self.product_doc_type.has_file:
            self.fields["details"].required = True

        # if the document is already expired, show the force_update checkbox
        # TODO: if the check to show force_update in case of errors in validate method is not working, try with this one
        # if self.instance.expiration_date and self.instance.expiration_date < timezone.now().date():
        #     self.fields['force_update'].widget = forms.CheckboxInput()

    def clean_file(self):
        file = self.cleaned_data.get("file", False)
        if file:
            if file.size > 10 * 1024 * 1024:  # file size limit: 10MB
                raise ValidationError("File size must not exceed 10MB.")
            # check that the file is a valid format (only images and pdf are accepted)
            # don't use file.content_type beasue it's not reliable. use mimetypes instead
            valid_file_types = ["image/jpeg", "image/png", "image/tiff", "application/pdf"]
            file_type = mimetypes.guess_type(file.name)[0]
            if file_type not in valid_file_types:
                raise ValidationError("File format not supported. Only images and pdf are accepted.")
        return file

    def clean_expiration_date(self):
        expiration_date = self.cleaned_data.get("expiration_date", False)
        if expiration_date:
            if expiration_date < timezone.now().date():
                raise ValidationError("Expiration date must not be in the past.")
        return expiration_date

    def clean(self):
        # Perform OCR if the user has checked the OCR checkbox
        cleaned_data = super().clean()

        # TODO: delete this, since we are using OCR via ajax call
        # ocr_check = cleaned_data.get("ocr_check", False)
        # file = cleaned_data.get("file", False)

        # if file and ocr_check:
        #     try:
        #         doc_metadata, mrz_data = extract_mrz_data(file)
        #         cleaned_data["metadata"] = doc_metadata
        #         cleaned_data["doc_number"] = mrz_data.get("document_number", False)
        #         cleaned_data["expiration_date"] = mrz_data.get("expiration_date", False)
        #     except Exception as e:
        #         self.add_error("file", str(e))
        # if we are forcing update, we don't need to check for errors
        force_update = cleaned_data.get("force_update", False)
        if force_update:
            return cleaned_data
        # Check that the document is not expiring in less than prodcut.documents_min_validity days from this applicn's doc_date
        expiration_date = cleaned_data.get("expiration_date", False)
        if expiration_date:
            if expiration_date < timezone.now().date():
                raise self.add_error("expiration_date", "Expiration date must not be in the past.")
            doc_date = cleaned_data.get("doc_date", False)
            if doc_date:
                product = self.instance.doc_application.product
                if (expiration_date - doc_date).days < product.documents_min_validity:
                    self.add_error(
                        "expiration_date",
                        "Document is expiring in less than %d days from the application date."
                        % product.documents_min_validity,
                    )

        # if all required fields are filled, set completed to True
        if self.product_doc_type.has_file and self.product_doc_type.has_details:
            if cleaned_data.get("file", False) or cleaned_data.get("details", False):
                cleaned_data["completed"] = True
        elif self.product_doc_type.has_file and cleaned_data.get("file", False):
            cleaned_data["completed"] = True
        elif self.product_doc_type.has_details and cleaned_data.get("details", False):
            cleaned_data["completed"] = True
        else:
            cleaned_data["completed"] = False

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.completed = self.cleaned_data.get("completed", False)
        if commit:
            instance.save()
        return instance

    def is_valid(self):
        valid = super(RequiredDocumentUpdateForm, self).is_valid()
        # if the form is not valid, show the force_update checkbox
        if not valid:
            self.fields["force_update"].widget = forms.CheckboxInput()
        return valid
