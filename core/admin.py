from django.contrib import admin

from core.models import Settings


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = ("currency", "budget_mode", "require_login", "ai_provider")

    # Prevent creating a second row.
    def has_add_permission(self, request):  # type: ignore[override]
        return not Settings.objects.exists()
