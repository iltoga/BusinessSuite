"""
URL configuration for business_suite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from api import views as api_views
from core import views as core_views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

# Base URL patterns
# Home route can be a redirect to /admin/ when legacy Django views are disabled.
from django.views.generic import RedirectView, TemplateView

home_view = (
    RedirectView.as_view(url="/admin/", permanent=False)
    if getattr(settings, "DISABLE_DJANGO_VIEWS", False)
    else TemplateView.as_view(template_name="base_template.html")
)

base_urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("landing.urls")),
    path("customers/", include("customers.urls")),
    path("products/", include("products.urls")),
    path("customer_applications/", include("customer_applications.urls")),
    path("invoices/", include("invoices.urls")),
    path("payments/", include("payments.urls")),
    path("letters/", include("letters.urls")),
    path("reports/", include("reports.urls")),
    path("", home_view, name="home"),
    path("api/", include("api.urls")),
    # Backwards compatible v1 namespace used by some tests and external clients
    path("api/v1/", include(("api.urls", "api"), namespace="v1")),
    path("nested_admin/", include("nested_admin.urls")),
    path("unicorn/", include("django_unicorn.urls")),
    path("admin-tools/", include("admin_tools.urls")),
    # to serve media files in development (TODO: in production use nginx or S3)
]

# Include debug toolbar only in DEBUG mode to avoid template reverse issues in production
if settings.DEBUG:
    base_urlpatterns.append(path("__debug__/", include(("debug_toolbar.urls", "djdt"), namespace="djdt")))

urlpatterns = (
    base_urlpatterns
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
)
