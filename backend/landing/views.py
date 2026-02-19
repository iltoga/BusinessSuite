from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect


class ConditionalLoginView(auth_views.LoginView):
    """Login view for Django admin access. Redirects to /admin/ after successful login."""

    template_name = "registration/login_simple.html"

    def get_success_url(self):
        return "/admin/"


def logout_view(request):
    logout(request)
    return redirect("login")
