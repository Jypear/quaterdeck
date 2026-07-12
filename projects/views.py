"""Project views: list/detail (container view) plus full CRUD.

Plain full-page forms + redirect, not HTMX modals — smallest correct CRUD,
matching the budget app's pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from projects.forms import ProjectForm
from projects.models import Project

if TYPE_CHECKING:
    from django.http import HttpResponse


class ProjectListView(ListView):
    model = Project
    template_name = "projects/list.html"
    context_object_name = "projects"


class ProjectDetailView(DetailView):
    model = Project
    template_name = "projects/detail.html"
    context_object_name = "project"
    queryset = Project.objects.prefetch_related("tasks", "notes")


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
