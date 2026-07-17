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


class IncomeStreamForm(_BootstrapModelForm):
    class Meta:
        model = IncomeStream
        fields: ClassVar[list[str]] = ["name", "amount", "frequency", "account"]


class OutgoingForm(_BootstrapModelForm):
    class Meta:
        model = Outgoing
        fields: ClassVar[list[str]] = ["name", "amount", "frequency", "category", "account"]


class TransferForm(_BootstrapModelForm):
    class Meta:
        model = Transfer
        fields: ClassVar[list[str]] = ["name", "amount", "frequency", "from_account", "to_account"]


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
