from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = "moviegame"

urlpatterns = [
    path("", views.game_view, name="game"),
    path("stats/", views.stats_view, name="stats"),
    path("panel/", views.admin_dashboard, name="admin_dashboard"),

    # API
    path("api/intentos/", views.api_registrar_intento, name="api_intentos"),
    path("api/autocomplete/", views.api_autocomplete, name="api_autocomplete"),

    # Auth
    path("login/", auth_views.LoginView.as_view(template_name="moviegame/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="moviegame:login"), name="logout"),
    path("register/", views.register_view, name="register"),
]
