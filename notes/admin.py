from django.contrib import admin

from notes.models import Note


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("title", "linked_project", "updated_at")
    list_filter = ("linked_project",)
    search_fields = ("title", "body")
