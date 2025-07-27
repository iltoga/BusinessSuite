from django import forms

from customer_applications.models import DocApplication, Document, DocWorkflow

from .doc_workflow import DocWorkflowForm
from .document import DocumentCreateForm, DocumentUpdateForm

DocumentCreateFormSet = forms.inlineformset_factory(
    DocApplication,  # parent model
    Document,  # child model
    form=DocumentCreateForm,  # form to use
    extra=0,  # minimum number of forms to show
    max_num=20,  # maximum number of forms to show
    can_delete=False,  # enable deletion
)


DocumentUpdateFormSet = forms.inlineformset_factory(
    DocApplication,  # parent model
    Document,  # child model
    form=DocumentUpdateForm,  # form to use
    extra=0,  # minimum number of forms to show
    max_num=20,  # maximum number of forms to show
    can_delete=False,  # enable deletion
)


DocWorkflowCreateFormSet = forms.inlineformset_factory(
    DocApplication,  # parent model
    DocWorkflow,  # child model
    form=DocWorkflowForm,  # form to use
    extra=0,  # minimum number of forms to show
    max_num=10,  # maximum number of forms to show
    can_delete=False,  # enable deletion
)
