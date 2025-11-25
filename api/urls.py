from django.urls import include, path
from rest_framework.authtoken import views as auth_views

from . import views

urlpatterns = [
    path("api-token-auth/", auth_views.obtain_auth_token),
    path("session-auth/", include("rest_framework.urls", namespace="rest_framework")),
    path("customers/", views.CustomersView.as_view()),
    path("customers/<int:pk>/", views.CustomerDetailView.as_view(), name="api-customer-detail"),
    # the view requires a 'q' parameter with the query string
    path("customers/search/", views.SearchCustomers.as_view(), name="api-customer-search"),
    path("products/", views.ProductsView.as_view()),
    path("products/get_product_by_id/<int:product_id>/", views.ProductByIDView.as_view(), name="api-product-by-id"),
    path("products/get_products_by_product_type/<str:product_type>/", views.ProductsByTypeView.as_view()),
    path(
        "invoices/get_customer_applications/<int:customer_id>/",
        views.CustomerApplicationsView.as_view(),
        name="api-customer-applications",
    ),
    path(
        "invoices/get_invoice_application_due_amount/<int:invoice_application_id>/",
        views.InvoiceApplicationDueAmountView.as_view(),
        name="api-invoice-application-due-amount",
    ),
    path("ocr/check/", views.OCRCheckView.as_view(), name="api-ocr-check"),
    path(
        "compute/doc_workflow_due_date/<int:task_id>/<slug:start_date>/",
        views.ComputeDocworkflowDueDate.as_view(),
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
]
