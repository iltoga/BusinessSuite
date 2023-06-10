from customer_applications.models import DocApplication, RequiredDocument, DocWorkflow
from django import forms
from .required_document import RequiredDocumentCreateForm, RequiredDocumentUpdateForm
from .doc_workflow import DocWorkflowForm

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