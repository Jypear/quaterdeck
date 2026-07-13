"""Budget views: overview, per-account, and pot-progress pages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, TemplateView, UpdateView

from budget.forms import (
    AccountForm,
    IncomeStreamForm,
    OneOffOutgoingForm,
    OutgoingCategoryForm,
    OutgoingForm,
    OutgoingVarianceForm,
    PotEntryForm,
    PotForm,
    TransferForm,
)
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
from budget.services import (
    account_summary,
    active_period,
    budget_summary,
    pot_progress,
)
from core.models import Settings

if TYPE_CHECKING:
    from decimal import Decimal

    from django.http import HttpRequest, HttpResponse


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


def _accounts_context(mode: str, settings: Settings) -> dict[str, Any]:
    """Context for the accounts page/partial, shared with `log_variance`'s HTMX re-render.

    Each outgoing gets a `.variance` attribute (the current period's
    OutgoingVariance, or None) set directly on the prefetched instance —
    simpler than a template dict-lookup filter.
    """
    period = active_period(mode, settings.budget_start_day)
    accounts = Account.objects.filter(is_active=True).prefetch_related(
        "income_streams",
        "outgoings",
        "transfers_in",
        "transfers_out",
        "one_off_outgoings",
    )
    variances = {
        v.outgoing_id: v
        for v in OutgoingVariance.objects.filter(period_start__gte=period.start, period_start__lt=period.end)
    }
    accounts = list(accounts)
    for account in accounts:
        for outgoing in account.outgoings.all():
            outgoing.variance = variances.get(outgoing.id)

    return {
        "mode": mode,
        "mode_choices": Settings.BudgetMode.choices,
        "account_summaries": [account_summary(a, mode, period) for a in accounts],
        "currency": settings.currency,
    }


def _pots_context(settings: Settings) -> dict[str, Any]:
    """Context for the pots page/partial, shared with `log_pot_entry`'s HTMX re-render.

    Each pot gets a `.current_entry` attribute (this period's PotEntry, or
    None) so the logging form can show/prefill what's already recorded.
    """
    period = active_period(settings.budget_mode, settings.budget_start_day)
    pots = list(Pot.objects.select_related("linked_project", "linked_one_off").prefetch_related("entries"))
    entries = {
        e.pot_id: e for e in PotEntry.objects.filter(period_start__gte=period.start, period_start__lt=period.end)
    }
    for pot in pots:
        pot.current_entry = entries.get(pot.id)

    return {
        "pot_progress": [pot_progress(pot, settings.budget_mode, period) for pot in pots],
        "currency": settings.currency,
    }


class AccountListView(TemplateView):
    def get_template_names(self) -> list[str]:
        return ["budget/_accounts.html"] if _is_partial_request(self.request) else ["budget/accounts.html"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        settings = Settings.get()
        mode = _requested_mode(self.request, settings)
        context.update(_accounts_context(mode, settings))
        if not _is_partial_request(self.request):
            context["categories"] = OutgoingCategory.objects.all()
        return context


class PotListView(TemplateView):
    template_name = "budget/pots.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(_pots_context(Settings.get()))
        return context


# --- Account / IncomeStream / Outgoing CRUD --------------------------------
#
# Plain full-page forms + redirect, not HTMX modals — smallest correct CRUD.
# ponytail: full-page CBV CRUD, HTMX modals if inline editing is wanted later.


class _BudgetFormMixin:
    """Shared template + page title + success message + redirect-to-accounts for CRUD views."""

    template_name = "budget/_form.html"
    success_url = reverse_lazy("budget:accounts")
    success_message = "Saved."
    title = ""

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("title", self.title)
        context.setdefault("cancel_url", self.success_url)
        return context

    def form_valid(self, form: Any) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response


class _PotFormMixin(_BudgetFormMixin):
    """Same as `_BudgetFormMixin` but redirects to the pots page, not accounts.

    Honors `?next=` (e.g. a project's detail page) so pots created/edited
    from that context return there instead of always landing on /pots/.
    """

    success_url = reverse_lazy("budget:pots")

    def get_success_url(self) -> str:
        next_url = self.request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()
        ):
            return next_url
        return str(self.success_url)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        next_url = self.request.GET.get("next")
        if next_url:
            context["cancel_url"] = next_url
        return context


class _AccountScopedCreateMixin:
    """Pre-selects `account` from `?account=<id>` on the add-income/add-outgoing links."""

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        account_id = self.request.GET.get("account")
        if account_id and account_id.isdigit():
            initial["account"] = account_id
        return initial


class _BudgetDeleteView(DeleteView):
    """Shared confirm-delete template + cancel_url for delete views."""

    template_name = "budget/_confirm_delete.html"
    success_url = reverse_lazy("budget:accounts")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("cancel_url", self.success_url)
        return context


class AccountCreateView(_BudgetFormMixin, CreateView):
    model = Account
    form_class = AccountForm
    title = "Add account"


class AccountUpdateView(_BudgetFormMixin, UpdateView):
    model = Account
    form_class = AccountForm
    title = "Edit account"


class AccountDeleteView(_BudgetDeleteView):
    model = Account


class IncomeStreamCreateView(_AccountScopedCreateMixin, _BudgetFormMixin, CreateView):
    model = IncomeStream
    form_class = IncomeStreamForm
    title = "Add income"


class IncomeStreamUpdateView(_BudgetFormMixin, UpdateView):
    model = IncomeStream
    form_class = IncomeStreamForm
    title = "Edit income"


class IncomeStreamDeleteView(_BudgetDeleteView):
    model = IncomeStream


class OutgoingCreateView(_AccountScopedCreateMixin, _BudgetFormMixin, CreateView):
    model = Outgoing
    form_class = OutgoingForm
    title = "Add outgoing"


class OutgoingUpdateView(_BudgetFormMixin, UpdateView):
    model = Outgoing
    form_class = OutgoingForm
    title = "Edit outgoing"


class OutgoingDeleteView(_BudgetDeleteView):
    model = Outgoing


class TransferCreateView(_BudgetFormMixin, CreateView):
    model = Transfer
    form_class = TransferForm
    title = "Add transfer"


class TransferUpdateView(_BudgetFormMixin, UpdateView):
    model = Transfer
    form_class = TransferForm
    title = "Edit transfer"


class TransferDeleteView(_BudgetDeleteView):
    model = Transfer


class OneOffOutgoingCreateView(_AccountScopedCreateMixin, _BudgetFormMixin, CreateView):
    model = OneOffOutgoing
    form_class = OneOffOutgoingForm
    title = "Add one-off outgoing"


class OneOffOutgoingUpdateView(_BudgetFormMixin, UpdateView):
    model = OneOffOutgoing
    form_class = OneOffOutgoingForm
    title = "Edit one-off outgoing"


class OneOffOutgoingDeleteView(_BudgetDeleteView):
    model = OneOffOutgoing


class OutgoingCategoryCreateView(_BudgetFormMixin, CreateView):
    model = OutgoingCategory
    form_class = OutgoingCategoryForm
    title = "Add category"


class OutgoingCategoryUpdateView(_BudgetFormMixin, UpdateView):
    model = OutgoingCategory
    form_class = OutgoingCategoryForm
    title = "Edit category"


class OutgoingCategoryDeleteView(_BudgetDeleteView):
    model = OutgoingCategory


class PotCreateView(_PotFormMixin, CreateView):
    model = Pot
    form_class = PotForm
    title = "Add pot"

    def get_initial(self) -> dict[str, Any]:
        """Pre-selects `linked_project` from `?linked_project=<id>` on the
        "Add pot to this project" link on a project's detail page."""
        initial = super().get_initial()
        project_id = self.request.GET.get("linked_project")
        if project_id and project_id.isdigit():
            initial["linked_project"] = project_id
        return initial


class PotUpdateView(_PotFormMixin, UpdateView):
    model = Pot
    form_class = PotForm
    title = "Edit pot"


class PotDeleteView(_BudgetDeleteView):
    model = Pot
    success_url = reverse_lazy("budget:pots")


# --- Feedback-loop logging: actual spend / actual saved ---------------------
#
# Both key on (thing, period_start=active period) via update_or_create, so
# re-submitting for the same period overwrites — that's also the correction
# path, no separate edit UI needed.


@require_POST
def log_variance(request: HttpRequest, outgoing_id: int) -> HttpResponse:
    outgoing = get_object_or_404(Outgoing, pk=outgoing_id)
    settings = Settings.get()
    period = active_period(settings.budget_mode, settings.budget_start_day)

    form = OutgoingVarianceForm(request.POST)
    if form.is_valid():
        OutgoingVariance.objects.update_or_create(
            outgoing=outgoing,
            period_start=period.start,
            defaults={"actual_amount": form.cleaned_data["actual_amount"]},
        )
        messages.success(request, f"Logged actual spend for {outgoing.name}.")

    mode = _requested_mode(request, settings)
    return render(request, "budget/_accounts.html", _accounts_context(mode, settings))


@require_POST
def log_pot_entry(request: HttpRequest, pot_id: int) -> HttpResponse:
    pot = get_object_or_404(Pot, pk=pot_id)
    settings = Settings.get()
    period = active_period(settings.budget_mode, settings.budget_start_day)

    form = PotEntryForm(request.POST)
    if form.is_valid():
        PotEntry.objects.update_or_create(
            pot=pot,
            period_start=period.start,
            defaults={"actual_amount": form.cleaned_data["actual_amount"]},
        )
        messages.success(request, f"Logged saved amount for {pot.name}.")

    return render(request, "budget/_pots.html", _pots_context(settings))
