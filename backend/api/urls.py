"""
API URL Configuration for BusinessSuite

This module defines the URL patterns for the REST API endpoints used by the Angular SPA frontend.
These are DRF (Django REST Framework) ViewSets and views that provide JSON API responses,
contrasting with legacy Django views that render HTML templates.

Key differences from legacy Django views:
- These endpoints return JSON data for Angular components, not HTML
- Authentication uses token-based auth (rest_framework.authtoken) for SPA
- Content negotiation handled by DRF for JSON responses
- Used by Angular services via generated API clients (from OpenAPI schema)
- Business logic remains in Django backend, but presentation is handled by Angular

Migration context:
- Part of the ongoing migration from Django Templates to Angular 19+ SPA
- Follows specifications in copilot/specs/django-angular/
- API contracts defined in copilot/specs/django-angular/api-contract-examples.md
- Generated TypeScript clients used in frontend/ via bun run generate:api

Do not confuse with legacy Django views in templates/ directories that use Django Templates + Bootstrap.
"""

from core import views as core_views
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from . import views
from .views_admin import BackupsViewSet, ServerManagementViewSet, backup_restore_sse, backup_start_sse

# DRF Router for RESTful API endpoints
# These ViewSets provide CRUD operations for Angular frontend consumption
router = DefaultRouter()
router.register(r"customers", views.CustomerViewSet, basename="customers")
router.register(r"country-codes", views.CountryCodeViewSet, basename="country-codes")
router.register(r"document-types", views.DocumentTypeViewSet, basename="document-types")
router.register(r"products", views.ProductViewSet, basename="products")
router.register(r"customer-applications", views.CustomerApplicationViewSet, basename="customer-applications")
router.register(r"documents", views.DocumentViewSet, basename="documents")
router.register(r"invoices", views.InvoiceViewSet, basename="invoices")
router.register(r"payments", views.PaymentViewSet, basename="payments")
router.register(r"letters", views.LettersViewSet, basename="letters")
router.register(r"user-profile", views.UserProfileViewSet, basename="user-profile")
router.register(r"user-settings", views.UserSettingsViewSet, basename="user-settings")
router.register(r"ocr", views.OCRViewSet, basename="ocr")
router.register(r"document-ocr", views.DocumentOCRViewSet, basename="document-ocr")
router.register(r"compute", views.ComputeViewSet, basename="compute")
router.register(r"dashboard-stats", views.DashboardStatsView, basename="dashboard-stats")

# Google Calendar & Tasks integration
from .google_views import GoogleCalendarViewSet, GoogleTasksViewSet

router.register(r"calendar", GoogleCalendarViewSet, basename="calendar")
router.register(r"tasks", GoogleTasksViewSet, basename="tasks")

# Admin tools (superuser only) - used by Angular admin components
router.register(r"backups", BackupsViewSet, basename="backups")
router.register(r"server-management", ServerManagementViewSet, basename="server-management")

urlpatterns = [
    # OpenAPI schema endpoints for API documentation and client generation
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Authentication endpoints
    path("api-token-auth/", views.TokenAuthView.as_view(), name="api-token-auth"),
    path("session-auth/", include("rest_framework.urls", namespace="rest_framework")),
    # SSE endpoints (plain Django views, bypass DRF content negotiation)
    # Used for real-time updates in Angular components
    path("backups/start/", backup_start_sse, name="api-backup-start-sse"),
    path("backups/restore/", backup_restore_sse, name="api-backup-restore-sse"),
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
    # These provide backward compatibility but are primarily for Angular consumption
    path(
        "customers/<int:pk>/",
        views.CustomerViewSet.as_view(
            {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
        ),
        name="api-customer-detail",
    ),
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
    # Explicitly declare invoice async routes with UUID path converters so drf-spectacular
    # can infer the path parameter type and avoid warning messages.
    path(
        "invoices/download-async/status/<uuid:job_id>/",
        views.InvoiceViewSet.as_view({"get": "download_async_status"}),
        name="invoices-download-async-status",
    ),
    path(
        "invoices/download-async/stream/<uuid:job_id>/",
        views.InvoiceViewSet.as_view({"get": "download_async_stream"}),
        name="invoices-download-async-stream",
    ),
    path(
        "invoices/download-async/file/<uuid:job_id>/",
        views.InvoiceViewSet.as_view({"get": "download_async_file"}),
        name="invoices-download-async-file",
    ),
    path(
        "invoices/import/status/<uuid:job_id>/",
        views.InvoiceViewSet.as_view({"get": "import_job_status"}),
        name="invoices-import-status",
    ),
    # exec_cron_jobs - utility endpoint for Angular admin tools
    path("cron/exec_cron_jobs/", views.exec_cron_jobs, name="api-exec-cron-jobs"),
    # Quick create endpoints - used by Angular forms for rapid data entry
    path("customers/quick-create/", views.customer_quick_create, name="api-customer-quick-create"),
    path("products/quick-create/", views.product_quick_create, name="api-product-quick-create"),
    path(
        "customer-applications/quick-create/",
        views.customer_application_quick_create,
        name="api-customer-application-quick-create",
    ),
    # Mock auth configuration - used for local development and testing
    path("mock-auth-config/", views.mock_auth_config, name="api-mock-auth-config"),
    # Public application configuration
    path("app-config/", core_views.public_app_config, name="api-public-app-config"),
    # Client-side logging endpoint (used in dev when frontend proxy forwards /api/client-logs)
    path("client-logs/", views.observability_log, name="api-client-logs"),
    # Include all router URLs - main REST API endpoints for Angular
    path("", include(router.urls)),
]
