"""Shared form helpers.

BootstrapModelForm applies Bootstrap widget classes so templates can render
`{{ field }}` directly (no django-widget-tweaks dependency).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms

if TYPE_CHECKING:
    from typing import Any


class BootstrapModelForm(forms.ModelForm):
    """Adds `form-control`/`form-select`/`form-check-input` to every widget."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")
