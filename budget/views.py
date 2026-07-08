"""Budget views: overview, per-account, and pot-progress pages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.views.generic import TemplateView

from budget.models import Account, Pot
from budget.services import (
    account_summary,
    active_period,
    budget_summary,
    pot_progress,
)
from core.models import Settings

if TYPE_CHECKING:
    from decimal import Decimal

    from django.http import HttpRequest


def _requested_mode(request: HttpRequest, settings: Settings) -> str:
    """The display mode for this request: `?mode=` override, else the instance default."""
    mode = request.GET.get("mode")
    valid_modes = {choice.value for choice in Settings.BudgetMode}
    return mode if mode in valid_modes else settings.budget_mode


def _requested_account_ids(request: HttpRequest) -> list[int] | None:
    """Account IDs selected via repeated `?accounts=` params, or None for "all"."""
    raw_ids = request.GET.getlist("accounts")
    if not raw_ids:
        return None
    return [int(value) for value in raw_ids if value.isdigit()]


def _is_partial_request(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _outgoings_percentage(income: Decimal, outgoings: Decimal) -> int:
    """Outgoings as a percentage of income, capped at 100 for the progress bar."""
    if income <= 0:
        return 100 if outgoings > 0 else 0
    return min(100, int(outgoings / income * 100))


class BudgetOverviewView(TemplateView):
    def get_template_names(self) -> list[str]:
        return ["budget/_summary.html"] if _is_partial_request(self.request) else ["budget/overview.html"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        settings = Settings.get()
        mode = _requested_mode(self.request, settings)
        account_ids = _requested_account_ids(self.request)
        period = active_period(mode, settings.budget_start_day)

        summary = budget_summary(mode, period, account_ids)

        context["mode"] = mode
        context["mode_choices"] = Settings.BudgetMode.choices
        context["all_accounts"] = Account.objects.filter(is_active=True)
        context["selected_account_ids"] = account_ids
        context["summary"] = summary
        context["currency"] = settings.currency
        context["outgoings_pct"] = _outgoings_percentage(summary.total_income, summary.total_outgoings)
        return context


class AccountListView(TemplateView):
    def get_template_names(self) -> list[str]:
        return ["budget/_accounts.html"] if _is_partial_request(self.request) else ["budget/accounts.html"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        settings = Settings.get()
        mode = _requested_mode(self.request, settings)
        period = active_period(mode, settings.budget_start_day)

        accounts = Account.objects.filter(is_active=True).prefetch_related(
            "income_streams",
            "outgoings",
            "transfers_in",
            "transfers_out",
            "one_off_outgoings",
        )

        context["mode"] = mode
        context["mode_choices"] = Settings.BudgetMode.choices
        context["account_summaries"] = [account_summary(a, mode, period) for a in accounts]
        context["currency"] = settings.currency
        return context


class PotListView(TemplateView):
    template_name = "budget/pots.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        settings = Settings.get()
        period = active_period(settings.budget_mode, settings.budget_start_day)

        pots = Pot.objects.select_related("linked_project", "linked_one_off").prefetch_related("entries")
        context["pot_progress"] = [pot_progress(pot, settings.budget_mode, period) for pot in pots]
        context["currency"] = settings.currency
        return context
