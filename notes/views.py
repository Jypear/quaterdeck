"""Note views: list/detail plus full CRUD and on-demand AI enrichment.

Plain full-page forms + redirect, not HTMX modals — smallest correct CRUD,
matching the tasks/projects pattern. Enrichment is the one HTMX bit: a button
posts to `enrich_note`, which renders a partial of suggested actions that can
each be applied with their own one-click POST.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from ai.providers import NullProvider, get_provider
from notes.ai import build_prompt, parse_actions
from notes.forms import NoteForm
from notes.models import Note
from projects.models import Project
from tasks.models import Task

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


class NoteListView(ListView):
    model = Note
    template_name = "notes/list.html"
    context_object_name = "notes"


class NoteDetailView(DetailView):
    model = Note
    template_name = "notes/detail.html"
    context_object_name = "note"


class _NoteFormMixin:
    """Shared template + page title + success message for CRUD views.

    No success_url — Note.get_absolute_url() sends Create/Update straight to
    the detail page, same as projects.
    """

    template_name = "notes/_form.html"
    success_message = "Saved."
    title = ""

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("title", self.title)
        context.setdefault("cancel_url", reverse_lazy("notes:list"))
        return context

    def form_valid(self, form: Any) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response


class NoteCreateView(_NoteFormMixin, CreateView):
    model = Note
    form_class = NoteForm
    title = "Add note"


class NoteUpdateView(_NoteFormMixin, UpdateView):
    model = Note
    form_class = NoteForm
    title = "Edit note"


class NoteDeleteView(DeleteView):
    model = Note
    template_name = "notes/_confirm_delete.html"
    success_url = reverse_lazy("notes:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("cancel_url", self.success_url)
        return context


@require_POST
def enrich_note(request: HttpRequest, pk: int) -> HttpResponse:
    """Send the note to the configured AI provider and render suggested actions.

    On-demand only — never triggered automatically, per Settings/AI design.
    """
    note = get_object_or_404(Note, pk=pk)
    provider = get_provider()
    if isinstance(provider, NullProvider):
        return render(request, "notes/_suggestions.html", {"note": note, "unconfigured": True})

    reply = provider.complete(build_prompt(note, Project.objects.all()))
    actions = parse_actions(reply)
    return render(request, "notes/_suggestions.html", {"note": note, "actions": actions})


@require_POST
def apply_action(request: HttpRequest, pk: int) -> HttpResponse:
    """Apply one suggested action (create a linked task, or link a project) to a note."""
    note = get_object_or_404(Note, pk=pk)
    action_type = request.POST.get("type")

    if action_type == "create_task":
        Task.objects.create(
            title=request.POST.get("title", ""),
            priority=request.POST.get("priority") or Task.Priority.MEDIUM,
            due_date=request.POST.get("due_date") or None,
            budget_amount=request.POST.get("budget_amount") or None,
            linked_project=note.linked_project,
        )
        messages.success(request, "Task created.")
    elif action_type == "link_project":
        note.linked_project = get_object_or_404(Project, pk=request.POST.get("project_id"))
        note.save(update_fields=["linked_project"])
        messages.success(request, "Note linked to project.")

    return redirect(note.get_absolute_url())
