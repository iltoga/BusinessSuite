import mimetypes

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from customer_applications.models import RequiredDocument


class RequiredDocumentCreateForm(forms.ModelForm):
    class Meta:
        model = RequiredDocument
        fields = ["doc_type"]


class RequiredDocumentUpdateForm(forms.ModelForm):
    # checkbox to force update even if there are errors. the field is hideen by default and shown only if there are errors
    force_update = forms.BooleanField(required=False, label="Force Update", widget=forms.HiddenInput())
    metadata = forms.JSONField(required=False, widget=forms.HiddenInput())
    # helper field to show the metadata in the template (it's a hidden field and could be used for testing purposes)
    metadata_display = forms.JSONField(required=False, disabled=True, label="Metadata", widget=forms.HiddenInput())
    # Only users with the 'upload_document' permission can upload documents
    field_permissions = {
        "file": ["upload_document"],
    }

    class Meta:
        model = RequiredDocument
        fields = [
            "doc_type",
            "file",
            "doc_number",
            "expiration_date",
            "details",
            "force_update",
            "metadata",
        ]
        widgets = {
            "expiration_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super(RequiredDocumentUpdateForm, self).__init__(*args, **kwargs)
        self.fields["doc_type"].disabled = True
        if self.instance.metadata:
            self.initial["metadata_display"] = self.instance.metadata
        else:
            # hide the field if there is no metadata
            self.initial["metadata_display"] = None

        if not self.instance.doc_type.has_expiration_date:
            self.fields["expiration_date"].widget = forms.HiddenInput()
        if not self.instance.doc_type.has_doc_number:
            self.fields["doc_number"].widget = forms.HiddenInput()
        if not self.instance.doc_type.has_file:
            self.fields["file"].widget = forms.HiddenInput()
        if not self.instance.doc_type.has_details:
            self.fields["details"].widget = forms.HiddenInput()
        if self.instance.doc_type.has_file and not self.instance.doc_type.has_details:
            self.fields["file"].required = True
        elif self.instance.doc_type.has_details and not self.instance.doc_type.has_file:
            self.fields["details"].required = True

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

        # if doc_type has_file and has_details, then at least one of them is required
        if self.instance.doc_type.has_file and self.instance.doc_type.has_details:
            cleaned_file = cleaned_data.get("file", False)
            cleaned_details = cleaned_data.get("details", False)
            if not cleaned_file and (not cleaned_details or cleaned_details == ""):
                self.add_error("file", "You have to fill in at least File or Details.")

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
        return cleaned_data

    def is_valid(self):
        valid = super(RequiredDocumentUpdateForm, self).is_valid()
        # if the form is not valid, show the force_update checkbox
        if not valid:
            self.fields["force_update"].widget = forms.CheckboxInput()
        return valid

    # if the required document.completed (we know it after saving it) is True and all other required documents of the doc_application are uploaded, set the satus of the fisrt doc_application's workflow (the one with task.step = 1) to "completed"
    def save(self, commit=True):
        required_document = super(RequiredDocumentUpdateForm, self).save(commit=True)
        doc_application = required_document.doc_application
        # find the first doc_application's workflow (the one with task.step = 1)
        if doc_application.workflows.filter(task__step=1).exists():
            workflow = doc_application.workflows.get(task__step=1)
            # check if all required documents of the doc_application are uploaded
            if doc_application.required_documents.filter(completed=False).exists():
                # if not, set the workflow status to "in progress"
                workflow.status = workflow.STATUS_PROCESSING
            else:
                # if yes, set the workflow status to "completed"
                workflow.status = workflow.STATUS_COMPLETED
            workflow.save()

        if commit:
            required_document.save()
        return required_document
