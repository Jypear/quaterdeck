"""HTML forms for budget CRUD and per-period logging.

Bootstrap classes are applied per-widget here (no django-widget-tweaks
dependency) so templates can just do `{{ field }}`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django import forms

from budget.models import Account, IncomeStream, Outgoing, OutgoingVariance, PotEntry

if TYPE_CHECKING:
    from typing import Any


class _BootstrapModelForm(forms.ModelForm):
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


class AccountForm(_BootstrapModelForm):
    class Meta:
        model = Account
        fields: ClassVar[list[str]] = ["name", "account_type", "is_active"]


class IncomeStreamForm(_BootstrapModelForm):
    class Meta:
        model = IncomeStream
        fields: ClassVar[list[str]] = ["name", "amount", "frequency", "account"]


class OutgoingForm(_BootstrapModelForm):
    class Meta:
        model = Outgoing
        fields: ClassVar[list[str]] = ["name", "amount", "frequency", "category", "account"]


class OutgoingVarianceForm(_BootstrapModelForm):
    """Only the actual amount is user input — outgoing/period_start are set
    server-side by the view (see log_variance)."""

    class Meta:
        model = OutgoingVariance
        fields: ClassVar[list[str]] = ["actual_amount"]


class PotEntryForm(_BootstrapModelForm):
    """Only the actual amount is user input — pot/period_start are set
    server-side by the view (see log_pot_entry)."""

    class Meta:
        model = PotEntry
        fields: ClassVar[list[str]] = ["actual_amount"]
