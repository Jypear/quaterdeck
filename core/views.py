"""Core views — dashboard and settings."""

from django.views.generic import TemplateView


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"
