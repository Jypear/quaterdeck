from django.urls import path

from core.views import CalendarView, DashboardView, SettingsUpdateView, regenerate_webhook_secret

app_name = "core"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("calendar/", CalendarView.as_view(), name="calendar"),
    path("settings/", SettingsUpdateView.as_view(), name="settings"),
    path("settings/regenerate-webhook-secret/", regenerate_webhook_secret, name="regenerate_webhook_secret"),
]
