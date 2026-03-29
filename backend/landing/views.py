"""
FILE_ROLE: View/controller logic for the landing app.

KEY_COMPONENTS:
- ConditionalLoginView: View/controller class.
- logout_view: Module symbol.

INTERACTIONS:
- Depends on: Django settings/bootstrap and adjacent app services or middleware in this module.

AI_GUIDELINES:
- Keep the file focused on its narrow responsibility and avoid mixing in unrelated business logic.
- Preserve existing runtime contracts for app routing, model behavior, and service boundaries.
"""

from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect


class ConditionalLoginView(auth_views.LoginView):
    """Login view for Django admin access. Redirects to /admin/ after successful login."""

    template_name = "registration/login_simple.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return "/admin/"


def logout_view(request):
    logout(request)
    return redirect("login")
