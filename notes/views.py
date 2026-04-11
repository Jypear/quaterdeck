"""Notes views — stubs to be fleshed out."""

from django.views.generic import DetailView, ListView

from notes.models import Note


class NoteListView(ListView):
    model = Note
    template_name = "notes/list.html"
    context_object_name = "notes"


class NoteDetailView(DetailView):
    model = Note
    template_name = "notes/detail.html"
    context_object_name = "note"
