from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


def home(request):
    return render(request, "landing/home.html")


class ConditionalLoginView(auth_views.LoginView):
    """Login view that redirects to admin when Django views are disabled.

    When `DISABLE_DJANGO_VIEWS` is True, use a simplified login template that
    doesn't include the main site navbar or JS dependencies that rely on jQuery.
    """

    def get_success_url(self):
        if getattr(settings, "DISABLE_DJANGO_VIEWS", False):
            return "/admin/"
        return super().get_success_url()

    def get_template_names(self):
        if getattr(settings, "DISABLE_DJANGO_VIEWS", False):
            return ["registration/login_simple.html"]
        return super().get_template_names()


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")
