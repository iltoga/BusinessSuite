"""
URL configuration for business_suite project.

All legacy Django template views have been removed. Only the DRF API, Django admin,
and auth (login/logout) routes remain.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("nested_admin/", include("nested_admin.urls")),
    # Login / logout for Django admin access
    path("", include("landing.urls")),
    # Root redirects to admin
    path("", RedirectView.as_view(url="/admin/", permanent=False), name="home"),
    # DRF API endpoints consumed by Angular SPA
    path("api/", include("api.urls")),
    # Backwards-compatible v1 namespace used by some tests and external clients
    path("api/v1/", include(("api.urls", "api"), namespace="v1")),
]

# Include debug toolbar only in DEBUG mode
if settings.DEBUG:
    urlpatterns.append(path("__debug__/", include(("debug_toolbar.urls", "djdt"), namespace="djdt")))

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
