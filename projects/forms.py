"""HTML forms for project CRUD."""

from __future__ import annotations

from typing import ClassVar

from core.forms import BootstrapModelForm
from projects.models import Project


class ProjectForm(BootstrapModelForm):
    class Meta:
        model = Project
        fields: ClassVar[list[str]] = ["name", "description", "budget"]
