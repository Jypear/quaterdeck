"""Task views — stubs to be fleshed out."""

from django.db.models import QuerySet
from django.views.generic import ListView

from tasks.models import Task


class TaskListView(ListView):
    model = Task
    template_name = "tasks/list.html"
    context_object_name = "tasks"

    def get_queryset(self) -> QuerySet[Task]:
        return Task.objects.exclude(status=Task.Status.DONE)
