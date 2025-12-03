from django.urls import path
from django.views.generic import DetailView

from customer_applications.models.doc_workflow import DocWorkflow

from .views import (
    ApplicationDocumentMergeView,
    DocApplicationCreateView,
    DocApplicationDeleteAllView,
    DocApplicationDeleteView,
    DocApplicationDetailView,
    DocApplicationListView,
    DocApplicationUpdateView,
    DocumentDetailView,
    DocumentDetailViewPrint,
    DocumentMergeDownloadView,
    DocumentUpdateView,
    DocWorkflowCreateView,
    DocWorkflowUpdateView,
)

urlpatterns = [
    path(
        "list/",
        DocApplicationListView.as_view(),
        name="customer-application-list",
    ),
    path(
        "create/",
        DocApplicationCreateView.as_view(),
        name="customer-application-create",
    ),
    path(
        "create_from_customer/<int:customer_pk>",
        DocApplicationCreateView.as_view(),
        name="customer-application-create-from-customer",
    ),
    path(
        "detail/<int:pk>/",
        DocApplicationDetailView.as_view(),
        name="customer-application-detail",
    ),
    path(
        "update/<int:pk>/",
        DocApplicationUpdateView.as_view(),
        name="customer-application-update",
    ),
    path(
        "update_document/<int:pk>/",
        DocumentUpdateView.as_view(),
        name="customer-application-document-update",
    ),
    path(
        "document_detail/<int:pk>/",
        DocumentDetailView.as_view(),
        name="customer-application-document-detail",
    ),
    path(
        "document_detail_print/<int:pk>/",
        DocumentDetailViewPrint.as_view(),
        name="customer-application-document-detail-print",
    ),
    path(
        "documents/merge/",
        DocumentMergeDownloadView.as_view(),
        name="customer-application-documents-merge",
    ),
    path(
        "detail/<int:pk>/merge-all/",
        ApplicationDocumentMergeView.as_view(),
        name="customer-application-merge-all",
    ),
    path(
        "create_doc_workflow/<int:docapplication_pk>/<int:step_no>",
        DocWorkflowCreateView.as_view(),
        name="customer-application-docworkflow-create",
    ),
    path(
        "update_doc_workflow/<int:pk>",
        DocWorkflowUpdateView.as_view(),
        name="customer-application-docworkflow-update",
    ),
    path(
        "doc_workflow_detail/<int:pk>/",
        DetailView.as_view(model=DocWorkflow, template_name="customer_applications/docworkflow_detail.html"),
        name="customer-application-docworkflow-detail",
    ),
    path(
        "delete/<int:pk>/",
        DocApplicationDeleteView.as_view(),
        name="customer-application-delete",
    ),
    path(
        "delete-all/",
        DocApplicationDeleteAllView.as_view(),
        name="customer-application-delete-all",
    ),
]
