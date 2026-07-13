"""Quaterdeck root URL configuration."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Auth
    path(
        "auth/login/",
        auth_views.LoginView.as_view(template_name="core/login.html"),
        name="login",
    ),
    path("auth/logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Apps
    path("", include("core.urls")),
    path("budget/", include("budget.urls")),
    path("projects/", include("projects.urls")),
    path("tasks/", include("tasks.urls")),
    path("notes/", include("notes.urls")),
    path("webhooks/", include("webhooks.urls")),
    # API
    path("api/", include("api.urls")),
]
