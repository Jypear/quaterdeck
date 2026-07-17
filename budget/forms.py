"""HTML forms for budget CRUD and per-period logging.

Bootstrap classes are applied per-widget here (no django-widget-tweaks
dependency) so templates can just do `{{ field }}`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django import forms

from budget.models import (
    Account,
    IncomeStream,
    OneOffOutgoing,
    Outgoing,
    OutgoingCategory,
    OutgoingVariance,
    Pot,
    PotEntry,
    Transfer,
)
from core.forms import BootstrapModelForm as _BootstrapModelForm

if TYPE_CHECKING:
    from typing import Any


class AccountForm(_BootstrapModelForm):
    class Meta:
        model = Account
        fields: ClassVar[list[str]] = ["name", "account_type", "is_active"]


_RECURRING_SCHEDULE_FIELDS: list[str] = ["recurring_day", "weekend_adjust", "week_interval", "week_anchor"]
_RECURRING_SCHEDULE_WIDGETS: dict[str, Any] = {
    # x-model drives the weekly/monthly x-show toggles in templates/budget/_form.html.
    "frequency": forms.Select(attrs={"x-model": "frequency"}),
    "week_anchor": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
}


class _RecurringScheduleCleanMixin(forms.ModelForm):
    """Shared validation for the FrequencyMixin scheduling fields."""

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        frequency = cleaned_data.get("frequency")
        recurring_day = cleaned_data.get("recurring_day")
        week_interval = cleaned_data.get("week_interval") or 1
        week_anchor = cleaned_data.get("week_anchor")

        if recurring_day is not None:
            max_day = 7 if frequency == "weekly" else 31
            if not (1 <= recurring_day <= max_day):
                self.add_error("recurring_day", f"Must be between 1 and {max_day} for {frequency} frequency.")

        if week_interval > 1 and week_anchor is None:
            self.add_error("week_anchor", "Required when the interval is more than 1 week.")

        return cleaned_data


class IncomeStreamForm(_RecurringScheduleCleanMixin, _BootstrapModelForm):
    class Meta:
        model = IncomeStream
        fields: ClassVar[list[str]] = ["name", "amount", "frequency", "account", *_RECURRING_SCHEDULE_FIELDS]
        widgets: ClassVar[dict[str, Any]] = _RECURRING_SCHEDULE_WIDGETS


class OutgoingForm(_RecurringScheduleCleanMixin, _BootstrapModelForm):
    class Meta:
        model = Outgoing
        fields: ClassVar[list[str]] = [
            "name",
            "amount",
            "frequency",
            "category",
            "account",
            *_RECURRING_SCHEDULE_FIELDS,
        ]
        widgets: ClassVar[dict[str, Any]] = _RECURRING_SCHEDULE_WIDGETS


class TransferForm(_RecurringScheduleCleanMixin, _BootstrapModelForm):
    class Meta:
        model = Transfer
        fields: ClassVar[list[str]] = [
            "name",
            "amount",
            "frequency",
            "from_account",
            "to_account",
            *_RECURRING_SCHEDULE_FIELDS,
        ]
        widgets: ClassVar[dict[str, Any]] = _RECURRING_SCHEDULE_WIDGETS


class OneOffOutgoingForm(_BootstrapModelForm):
    class Meta:
        model = OneOffOutgoing
        fields: ClassVar[list[str]] = ["name", "amount", "due_date", "account", "linked_pot"]
        widgets: ClassVar[dict[str, Any]] = {
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


class OutgoingCategoryForm(_BootstrapModelForm):
    class Meta:
        model = OutgoingCategory
        fields: ClassVar[list[str]] = ["name"]


class PotForm(_BootstrapModelForm):
    class Meta:
        model = Pot
        fields: ClassVar[list[str]] = [
            "name",
            "target_amount",
            "target_date",
            "monthly_target",
            "linked_project",
            "linked_one_off",
        ]
        widgets: ClassVar[dict[str, Any]] = {
            "target_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


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
