import os
import tempfile
from datetime import datetime
from io import StringIO

from django.contrib import admin, messages
from django.core.management import call_command
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path

from core.models import Settings

# App labels worth backing up. contenttypes/permissions/sessions/admin log
# entries are excluded — their PKs are regenerated on migrate and dumping
# them causes loaddata conflicts.
BACKUP_APPS = ("auth.user", "core", "budget", "projects", "tasks", "notes", "webhooks")


def backup_view(request):  # noqa: ARG001 (admin_view requires the request signature)
    buffer = StringIO()
    call_command("dumpdata", *BACKUP_APPS, indent=2, stdout=buffer)
    filename = f"quaterdeck-backup-{datetime.now():%Y%m%d-%H%M%S}.json"
    response = HttpResponse(buffer.getvalue(), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def restore_view(request):
    if request.method == "POST":
        upload = request.FILES.get("backup_file")
        if not upload:
            messages.error(request, "Choose a backup file to restore.")
            return redirect("admin:restore")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            for chunk in upload.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            call_command("loaddata", tmp_path)
        except Exception as exc:
            messages.error(request, f"Restore failed: {exc}")
        else:
            messages.success(request, "Backup restored successfully.")
        finally:
            os.unlink(tmp_path)
        return redirect("admin:index")

    context = {**admin.site.each_context(request), "title": "Restore backup"}
    return render(request, "admin/restore.html", context)


_original_get_urls = admin.site.get_urls


def _get_urls():
    return [
        path("backup/", admin.site.admin_view(backup_view), name="backup"),
        path("restore/", admin.site.admin_view(restore_view), name="restore"),
        *_original_get_urls(),
    ]


admin.site.get_urls = _get_urls


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = ("currency", "budget_mode", "require_login", "ai_provider")

    # Prevent creating a second row.
    def has_add_permission(self, request):  # type: ignore[override]
        return not Settings.objects.exists()
