from django.urls import path

from notes import views

app_name = "notes"

urlpatterns = [
    path("", views.NoteListView.as_view(), name="list"),
    path("<int:pk>/", views.NoteDetailView.as_view(), name="detail"),
    # Note CRUD
    path("note/add/", views.NoteCreateView.as_view(), name="note_add"),
    path("note/<int:pk>/edit/", views.NoteUpdateView.as_view(), name="note_edit"),
    path("note/<int:pk>/delete/", views.NoteDeleteView.as_view(), name="note_delete"),
    # AI: suggestions (link/create) + enrichment (rewrite/research)
    path("note/<int:pk>/suggest/", views.suggest_note, name="note_suggest"),
    path("note/<int:pk>/apply-action/", views.apply_action, name="note_apply_action"),
    path("note/<int:pk>/enrich/", views.enrich_note, name="note_enrich"),
    path("note/<int:pk>/enrich/apply/", views.enrich_apply, name="note_enrich_apply"),
    path("render-markdown/", views.render_markdown_preview, name="render_markdown"),
]
