from django.urls import include, path
from rest_framework.authtoken import views as auth_views
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"customers", views.CustomerViewSet, basename="customers")
router.register(r"products", views.ProductViewSet, basename="products")
router.register(r"invoices", views.InvoiceViewSet, basename="invoices")
router.register(r"ocr", views.OCRViewSet, basename="ocr")
router.register(r"document-ocr", views.DocumentOCRViewSet, basename="document-ocr")
router.register(r"compute", views.ComputeViewSet, basename="compute")

urlpatterns = [
    path("api-token-auth/", auth_views.obtain_auth_token),
    path("session-auth/", include("rest_framework.urls", namespace="rest_framework")),
    path("ocr/check/", views.OCRViewSet.as_view({"post": "check"}), name="api-ocr-check"),
    path("ocr/status/<uuid:job_id>/", views.OCRViewSet.as_view({"get": "status"}), name="api-ocr-status"),
    path(
        "document-ocr/check/",
        views.DocumentOCRViewSet.as_view({"post": "check"}),
        name="api-document-ocr-check",
    ),
    path(
        "document-ocr/status/<uuid:job_id>/",
        views.DocumentOCRViewSet.as_view({"get": "status"}),
        name="api-document-ocr-status",
    ),
    # Compatibility aliases for template tags
    path("customers/<int:pk>/", views.CustomerViewSet.as_view({"get": "retrieve"}), name="api-customer-detail"),
    path("customers/search/", views.CustomerViewSet.as_view({"get": "search"}), name="api-customer-search"),
    path(
        "products/get_product_by_id/<int:product_id>/",
        views.ProductViewSet.as_view({"get": "get_product_by_id"}),
        name="api-product-by-id",
    ),
    path(
        "invoices/get_customer_applications/<int:customer_id>/",
        views.InvoiceViewSet.as_view({"get": "get_customer_applications"}),
        name="api-customer-applications",
    ),
    path(
        "invoices/get_invoice_application_due_amount/<int:invoice_application_id>/",
        views.InvoiceViewSet.as_view({"get": "get_invoice_application_due_amount"}),
        name="api-invoice-application-due-amount",
    ),
    path(
        "compute/doc_workflow_due_date/<int:task_id>/<slug:start_date>/",
        views.ComputeViewSet.as_view({"get": "doc_workflow_due_date"}),
        name="api-compute-docworkflow-due-date",
    ),
    # exec_cron_jobs
    path("cron/exec_cron_jobs/", views.exec_cron_jobs, name="api-exec-cron-jobs"),
    # customer quick create
    path("customers/quick-create/", views.customer_quick_create, name="api-customer-quick-create"),
    # product quick create
    path("products/quick-create/", views.product_quick_create, name="api-product-quick-create"),
    # customer application quick create
    path(
        "customer-applications/quick-create/",
        views.customer_application_quick_create,
        name="api-customer-application-quick-create",
    ),
    path("", include(router.urls)),
]
