from django.contrib import admin

from tasks.models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "priority", "status", "due_date", "linked_project")
    list_filter = ("priority", "status", "linked_project")
    search_fields = ("title",)
