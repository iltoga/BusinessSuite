from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


def home(request):
    return render(request, "landing/home.html")


class ConditionalLoginView(auth_views.LoginView):
    """Login view that redirects to admin when Django views are disabled."""

    def get_success_url(self):
        if getattr(settings, "DISABLE_DJANGO_VIEWS", False):
            return "/admin/"
        return super().get_success_url()


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")
