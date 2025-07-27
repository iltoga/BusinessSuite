from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


def home(request):
    return render(request, "landing/home.html")


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")
