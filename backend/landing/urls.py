"""
FILE_ROLE: URL routing for the landing app.

KEY_COMPONENTS:
- Module body: configuration, helpers, or script entrypoints.

INTERACTIONS:
- Depends on: Django settings/bootstrap and adjacent app services or middleware in this module.

AI_GUIDELINES:
- Keep the file focused on its narrow responsibility and avoid mixing in unrelated business logic.
- Preserve existing runtime contracts for app routing, model behavior, and service boundaries.
"""

from django.urls import path

from . import views

urlpatterns = [
    # path('', views.home, name='home'),
    path("login/", views.ConditionalLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
]
