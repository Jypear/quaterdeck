"""Project views: list/detail (container view) plus full CRUD.

Plain full-page forms + redirect, not HTMX modals — smallest correct CRUD,
matching the budget app's pattern.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.db.models import Count, Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, TemplateView, UpdateView

from budget.services import active_period, pot_progress
from core.models import Settings
from core.tables import apply_sort, is_partial
from projects.forms import ProjectForm
from projects.models import Project

if TYPE_CHECKING:
    from django.http import HttpResponse

_SORT_FIELDS = {"name": "name", "budget": "budget"}


class ProjectListView(TemplateView):
    def get_template_names(self) -> list[str]:
        return ["projects/_table.html"] if is_partial(self.request) else ["projects/list.html"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        params = self.request.GET
        projects = Project.objects.annotate(
            task_count=Count("tasks", distinct=True),
            note_count=Count("notes", distinct=True),
            pot_count=Count("pots", distinct=True),
        )

        q = params.get("q", "").strip()
        if q:
            projects = projects.filter(Q(name__icontains=q) | Q(description__icontains=q))

        projects, sort_col, sort_dir = apply_sort(params, projects, _SORT_FIELDS, default="name")

        context.update({"projects": projects, "q": q, "sort_col": sort_col, "sort_dir": sort_dir})
        return context


class ProjectDetailView(DetailView):
    model = Project
    template_name = "projects/detail.html"
    context_object_name = "project"
    queryset = Project.objects.prefetch_related("tasks", "notes", "pots__entries", "pots__linked_one_off")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        settings = Settings.get()
        period = active_period(settings.budget_mode, settings.budget_start_day)

        pot_rows = [pot_progress(pot, settings.budget_mode, period) for pot in self.object.pots.all()]
        total_saved = sum((row.saved_to_date for row in pot_rows), Decimal("0"))
        budget = self.object.budget
        budget_pct = int(total_saved / budget * 100) if budget else None

        context["pot_rows"] = pot_rows
        context["total_saved"] = total_saved
        context["budget_pct"] = budget_pct
        context["currency"] = settings.currency
        return context


class _ProjectFormMixin:
    """Shared template + page title + success message for CRUD views.

    No success_url — Project.get_absolute_url() sends Create/Update straight
    to the detail page.
    """

    template_name = "projects/_form.html"
    success_message = "Saved."
    title = ""

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("title", self.title)
        context.setdefault("cancel_url", reverse_lazy("projects:list"))
        return context

    def form_valid(self, form: Any) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response


class ProjectCreateView(_ProjectFormMixin, CreateView):
    model = Project
    form_class = ProjectForm
    title = "Add project"


class ProjectUpdateView(_ProjectFormMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    title = "Edit project"


class ProjectDeleteView(DeleteView):
    model = Project
    template_name = "projects/_confirm_delete.html"
    success_url = reverse_lazy("projects:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("cancel_url", self.success_url)
        return context
