from django import forms

from customer_applications.models import Document


class DocumentCreateForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["doc_type", "required"]


class DocumentUpdateForm(forms.ModelForm):
    force_update = forms.BooleanField(required=False, label="Force Update", widget=forms.HiddenInput())
    metadata = forms.JSONField(required=False, widget=forms.HiddenInput())
    metadata_display = forms.JSONField(required=False, disabled=True, label="Metadata", widget=forms.HiddenInput())

    class Meta:
        model = Document
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
        self.user = kwargs.pop("user", None)
        super(DocumentUpdateForm, self).__init__(*args, **kwargs)
        self.set_initial_fields()

    def clean(self):
        cleaned_data = super().clean()
        self.validate_doc_type_conditions(cleaned_data)
        self.validate_expiration_date(cleaned_data)
        return cleaned_data

    def is_valid(self):
        valid = super(DocumentUpdateForm, self).is_valid()
        if not valid:
            self.fields["force_update"].widget = forms.CheckboxInput()
        return valid

    def save(self, commit=True):
        document = super().save()
        self.update_doc_application_workflow(document)
        return document

    # Custom methods
    def set_initial_fields(self):
        self.fields["doc_type"].disabled = True
        self.initial["metadata_display"] = self.instance.metadata or None
        self.set_widget_fields()

    def set_widget_fields(self):
        doc_type = self.instance.doc_type
        if not doc_type.has_expiration_date:
            self.fields["expiration_date"].widget = forms.HiddenInput()
        if not doc_type.has_doc_number:
            self.fields["doc_number"].widget = forms.HiddenInput()
        if not doc_type.has_file:
            self.fields["file"].widget = forms.HiddenInput()
        if not doc_type.has_details:
            self.fields["details"].widget = forms.HiddenInput()
        if doc_type.has_file and not doc_type.has_details:
            self.fields["file"].required = True
        elif doc_type.has_details and not doc_type.has_file:
            self.fields["details"].required = True

    def validate_doc_type_conditions(self, cleaned_data):
        if self.instance.doc_type.name == "Passport":
            self.validate_passport_fields(cleaned_data)
        if self.instance.doc_type.has_file and self.instance.doc_type.has_details:
            self.validate_file_and_details(cleaned_data)

    def validate_passport_fields(self, cleaned_data):
        if not cleaned_data.get("doc_number", False):
            self.add_error("doc_number", "This field is required.")
        if not cleaned_data.get("expiration_date", False):
            self.add_error("expiration_date", "This field is required.")

    def validate_file_and_details(self, cleaned_data):
        if not cleaned_data.get("file", False) and not cleaned_data.get("details", False):
            self.add_error("file", "You have to fill in at least File or Details.")

    def validate_expiration_date(self, cleaned_data):
        if cleaned_data.get("force_update", False):
            return
        expiration_date = cleaned_data.get("expiration_date", False)
        doc_date = cleaned_data.get("doc_date", False)
        if expiration_date and doc_date:
            product = self.instance.doc_application.product
            if (expiration_date - doc_date).days < product.documents_min_validity:
                self.add_error(
                    "expiration_date",
                    f"Document is expiring in less than {product.documents_min_validity} days from the application date.",
                )

    def update_doc_application_workflow(self, document):
        doc_application = document.doc_application
        workflow_count = doc_application.workflows.filter(task__step=1).count()

        if workflow_count == 1:
            workflow = doc_application.workflows.get(task__step=1)
            if doc_application.is_document_collection_completed:
                workflow.status = workflow.STATUS_COMPLETED
            else:
                workflow.status = workflow.STATUS_PROCESSING

            workflow.save()
            workflow.doc_application.save()
