"""Note views: list/detail plus full CRUD and two on-demand AI features.

Plain full-page forms + redirect, not HTMX modals — smallest correct CRUD,
matching the tasks/projects pattern. The AI surface is split in two:

- `suggest_note` (HTMX): renders a partial of suggested links/actions that can
  each be applied with their own one-click POST via `apply_action`.
- `enrich_note` (streaming): rewrites the note body and streams the result as
  plain text chunks; the frontend previews it and only `enrich_apply` writes
  it back, so the original is never lost without confirmation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, TemplateView, UpdateView

from ai.providers import NullProvider, get_provider
from budget.models import OneOffOutgoing, Pot
from core.models import Settings
from core.tables import apply_sort, is_partial
from notes.ai import build_enrich_prompt, build_prompt, parse_actions
from notes.forms import NoteForm
from notes.markdown import render_markdown
from notes.models import Note
from projects.models import Project
from tasks.models import Task

if TYPE_CHECKING:
    from django.http import HttpRequest

_SORT_FIELDS = {"title": "title", "updated_at": "updated_at", "created_at": "created_at"}


class NoteListView(TemplateView):
    def get_template_names(self) -> list[str]:
        return ["notes/_table.html"] if is_partial(self.request) else ["notes/list.html"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        params = self.request.GET
        notes = Note.objects.all()

        q = params.get("q", "").strip()
        if q:
            notes = notes.filter(Q(title__icontains=q) | Q(body__icontains=q))

        project_id = params.get("linked_project", "")
        if project_id.isdigit():
            notes = notes.filter(linked_project_id=int(project_id))

        notes, sort_col, sort_dir = apply_sort(params, notes, _SORT_FIELDS, default="updated_at")

        context.update(
            {
                "notes": notes,
                "q": q,
                "linked_project": project_id,
                "all_projects": Project.objects.all(),
                "sort_col": sort_col,
                "sort_dir": sort_dir,
            }
        )
        return context


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
def suggest_note(request: HttpRequest, pk: int) -> HttpResponse:
    """Send the note to the configured AI provider and render suggested actions.

    On-demand only — never triggered automatically, per Settings/AI design.
    """
    note = get_object_or_404(Note, pk=pk)
    provider = get_provider()
    if isinstance(provider, NullProvider):
        return render(request, "notes/_suggestions.html", {"note": note, "unconfigured": True})

    prompt = build_prompt(note, Project.objects.all(), Pot.objects.all(), OneOffOutgoing.objects.all())
    reply = provider.complete(prompt, system=Settings.get().ai_system_prompt)
    actions = parse_actions(reply)
    return render(request, "notes/_suggestions.html", {"note": note, "actions": actions})


@require_POST
def apply_action(request: HttpRequest, pk: int) -> HttpResponse:
    """Apply one suggested action (create a task, link, or new project) to a note."""
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
    elif action_type == "link_pot":
        note.linked_pot = get_object_or_404(Pot, pk=request.POST.get("pot_id"))
        note.save(update_fields=["linked_pot"])
        messages.success(request, "Note linked to pot.")
    elif action_type == "link_one_off":
        note.linked_one_off = get_object_or_404(OneOffOutgoing, pk=request.POST.get("one_off_id"))
        note.save(update_fields=["linked_one_off"])
        messages.success(request, "Note linked to one-off payment.")
    elif action_type == "create_project":
        note.linked_project = Project.objects.create(
            name=request.POST.get("name", ""),
            description=request.POST.get("description", ""),
        )
        note.save(update_fields=["linked_project"])
        messages.success(request, "Project created and linked.")

    return redirect(note.get_absolute_url())


@require_POST
def enrich_note(request: HttpRequest, pk: int) -> HttpResponse:  # noqa: ARG001
    """Stream a rewritten/researched version of the note body as plain text chunks.

    Non-destructive: this only streams text back to the page for preview.
    Nothing is saved until the user confirms via `enrich_apply`.
    """
    note = get_object_or_404(Note, pk=pk)
    provider = get_provider()
    if isinstance(provider, NullProvider):

        def unconfigured() -> Any:
            yield "No AI provider configured. Set one up in Settings first."

        chunks = unconfigured()
    else:
        settings = Settings.get()
        chunks = provider.stream(
            build_enrich_prompt(note), web_search=settings.ai_web_search, system=settings.ai_system_prompt
        )

    response = StreamingHttpResponse(chunks, content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # ponytail: avoids proxy buffering; harmless if no proxy sits in front.
    return response


@require_POST
def enrich_apply(request: HttpRequest, pk: int) -> HttpResponse:
    """Replace the note body with the previewed, enriched text the user accepted."""
    note = get_object_or_404(Note, pk=pk)
    note.body = request.POST.get("body", "")
    note.save(update_fields=["body"])
    messages.success(request, "Note updated.")
    return redirect(note.get_absolute_url())


@require_POST
def render_markdown_preview(request: HttpRequest) -> HttpResponse:
    """Render arbitrary text as sanitised markdown HTML for the enrichment preview.

    Stateless — takes no note pk, just renders whatever text the client sends.
    """
    html = render_markdown(request.POST.get("text", ""))
    return HttpResponse(html, content_type="text/html; charset=utf-8")
