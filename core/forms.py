"""Shared form helpers.

BootstrapModelForm applies Bootstrap widget classes so templates can render
`{{ field }}` directly (no django-widget-tweaks dependency).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django import forms

from core.models import Settings

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


class SettingsForm(BootstrapModelForm):
    """Edits the singleton Settings row.

    ai_api_key is rendered as a password field that never echoes the stored
    value; leaving it blank on save keeps the existing key so re-saving other
    settings doesn't wipe it.
    """

    class Meta:
        model = Settings
        fields: ClassVar[list[str]] = [
            "currency",
            "budget_mode",
            "budget_start_day",
            "require_login",
            "ai_provider",
            "ai_api_key",
            "ai_model",
        ]
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "ai_api_key": forms.PasswordInput(render_value=False),
        }

    def clean_ai_api_key(self) -> str:
        new_value = self.cleaned_data["ai_api_key"]
        return new_value or self.instance.ai_api_key
