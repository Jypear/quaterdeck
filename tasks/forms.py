"""HTML forms for task CRUD."""

from __future__ import annotations

from typing import Any, ClassVar

from django import forms

from core.forms import BootstrapModelForm
from tasks.models import Task


class TaskForm(BootstrapModelForm):
    class Meta:
        model = Task
        fields: ClassVar[list[str]] = [
            "title",
            "due_date",
            "priority",
            "status",
            "linked_project",
            "budget_amount",
        ]
        widgets: ClassVar[dict[str, Any]] = {
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
