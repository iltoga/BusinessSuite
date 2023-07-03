"""
URL configuration for RevisBaliCRM project.

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
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("landing.urls")),
    path("customers/", include("customers.urls")),
    path("products/", include("products.urls")),
    path("customer_applications/", include("customer_applications.urls")),
    path("invoices/", include("invoices.urls")),
    path("", TemplateView.as_view(template_name="base_template.html"), name="home"),
    path("api/", include("api.urls")),
    path("nested_admin/", include("nested_admin.urls")),
    path("unicorn/", include("django_unicorn.urls")),
    path("__debug__/", include("debug_toolbar.urls")),
    # to serve media files in development (TODO: in production use nginx or S3)
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
