from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = "moviegame"

urlpatterns = [
    # Páginas
    path("", views.home_view, name="home"),
    path("play/", views.game_view, name="game"),
    path("stats/", views.stats_view, name="stats"),
    path("how-to/", views.howto_view, name="howto"),
    path("panel/", views.admin_dashboard, name="admin_dashboard"),
    path("panel/set-daily/", views.admin_set_daily, name="admin_set_daily"),

    # API
    path("api/intentos/", views.api_intentos, name="api_intentos"),
    path("api/autocomplete/", views.api_autocomplete, name="api_autocomplete"),

    # Auth
    path("login/", auth_views.LoginView.as_view(
        template_name="moviegame/login.html",
        redirect_authenticated_user=True
    ), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.register_view, name="register"),
    path("logout/", auth_views.LogoutView.as_view(next_page="moviegame:login"), name="logout"),
]
