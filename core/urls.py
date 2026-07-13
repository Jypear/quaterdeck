from django.urls import path

from core.views import CalendarView, DashboardView, SettingsUpdateView

app_name = "core"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("calendar/", CalendarView.as_view(), name="calendar"),
    path("settings/", SettingsUpdateView.as_view(), name="settings"),
]
