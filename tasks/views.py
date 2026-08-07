"""Task views: list (with done-toggle) plus full CRUD.

Plain full-page forms + redirect, not HTMX modals — smallest correct CRUD,
matching the budget app's pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, TemplateView, UpdateView

from core.tables import apply_sort, is_partial
from projects.models import Project
from tasks.forms import TaskForm
from tasks.models import Task

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

_SORT_FIELDS = {"title": "title", "due_date": "due_date", "priority": "priority", "status": "status"}


def _task_table_context(params: Any) -> dict[str, Any]:
    """Filtered + sorted task queryset and the filter state, from a GET/POST QueryDict.

    Shared by `TaskListView` and `toggle_done` so the toggle's HTMX re-render
    preserves whatever filters were active (it `hx-include`s the filter form).
    """
    tasks = Task.objects.all()

    q = params.get("q", "").strip()
    if q:
        tasks = tasks.filter(title__icontains=q)

    status = params.get("status", "")
    if status in Task.Status.values:
        tasks = tasks.filter(status=status)

    priority = params.get("priority", "")
    if priority in Task.Priority.values:
        tasks = tasks.filter(priority=priority)

    project_id = params.get("linked_project", "")
    if project_id.isdigit():
        tasks = tasks.filter(linked_project_id=int(project_id))

    tasks, sort_col, sort_dir = apply_sort(params, tasks, _SORT_FIELDS, default="due_date")

    return {
        "tasks": tasks,
        "q": q,
        "status": status,
        "priority": priority,
        "linked_project": project_id,
        "status_choices": Task.Status.choices,
        "priority_choices": Task.Priority.choices,
        "all_projects": Project.objects.all(),
        "sort_col": sort_col,
        "sort_dir": sort_dir,
    }


class TaskListView(TemplateView):
    def get_template_names(self) -> list[str]:
        return ["tasks/_table.html"] if is_partial(self.request) else ["tasks/list.html"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {**super().get_context_data(**kwargs), **_task_table_context(self.request.GET)}


class _TaskFormMixin:
    """Shared template + page title + success message + redirect for CRUD views."""

    template_name = "tasks/_form.html"
    success_url = reverse_lazy("tasks:list")
    success_message = "Saved."
    title = ""

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("title", self.title)
        context.setdefault("cancel_url", self.success_url)
        return context

    def form_valid(self, form: Any) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response


class TaskCreateView(_TaskFormMixin, CreateView):
    model = Task
    form_class = TaskForm
    title = "Add task"

    def get_initial(self) -> dict[str, Any]:
        """Pre-fills `due_date` from `?date=YYYY-MM-DD`, e.g. from the calendar's "+"."""
        initial = super().get_initial()
        date = parse_date(self.request.GET.get("date") or "")
        if date:
            initial["due_date"] = date
        return initial


class TaskUpdateView(_TaskFormMixin, UpdateView):
    model = Task
    form_class = TaskForm
    title = "Edit task"


class TaskDeleteView(DeleteView):
    model = Task
    template_name = "tasks/_confirm_delete.html"
    success_url = reverse_lazy("tasks:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("cancel_url", self.success_url)
        return context


@require_POST
def toggle_done(request: HttpRequest, pk: int) -> HttpResponse:
    """Flip a task done<->todo and re-render the table partial.

    Mirrors budget.views.log_pot_entry's re-render-in-place pattern. The toggle
    form `hx-include`s the filter form, so `request.POST` carries whatever
    filters/sort were active — the re-rendered table keeps them applied.
    """
    task = get_object_or_404(Task, pk=pk)
    task.status = Task.Status.TODO if task.status == Task.Status.DONE else Task.Status.DONE
    task.save(update_fields=["status"])
    return render(request, "tasks/_table.html", _task_table_context(request.POST))
