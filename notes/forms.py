"""HTML forms for note CRUD."""

from __future__ import annotations

from typing import ClassVar

from django import forms

from core.forms import BootstrapModelForm
from notes.models import Note


class NoteForm(BootstrapModelForm):
    class Meta:
        model = Note
        fields: ClassVar[list[str]] = ["title", "body", "linked_project"]
        widgets: ClassVar[dict[str, forms.Widget]] = {"body": forms.Textarea(attrs={"rows": 8})}
