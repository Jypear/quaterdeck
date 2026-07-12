"""Task views: list (with done-toggle) plus full CRUD.

Plain full-page forms + redirect, not HTMX modals — smallest correct CRUD,
matching the budget app's pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, TemplateView, UpdateView

from tasks.forms import TaskForm
from tasks.models import Task

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


def _is_partial_request(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _task_list_context() -> dict[str, Any]:
    return {
        "open_tasks": Task.objects.exclude(status=Task.Status.DONE),
        "done_tasks": Task.objects.filter(status=Task.Status.DONE),
    }


class TaskListView(TemplateView):
    def get_template_names(self) -> list[str]:
        return ["tasks/_list.html"] if _is_partial_request(self.request) else ["tasks/list.html"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {**super().get_context_data(**kwargs), **_task_list_context()}


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
    """Flip a task done<->todo and re-render the list partial.

    Mirrors budget.views.log_variance's re-render-in-place pattern.
    """
    task = get_object_or_404(Task, pk=pk)
    task.status = Task.Status.TODO if task.status == Task.Status.DONE else Task.Status.DONE
    task.save(update_fields=["status"])
    return render(request, "tasks/_list.html", _task_list_context())
