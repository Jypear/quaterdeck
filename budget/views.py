"""Budget views: overview, per-account, and pot-progress pages."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
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
    ZERO,
    AccountLane,
    FlowGraph,
    Period,
    _monthly_anchor,
    _shift_month,
    account_summary,
    account_timelines,
    active_period,
    budget_flow,
    budget_summary,
    outgoings_percentage,
    pot_progress,
    resolve_transfer_amounts,
    to_display,
)
from core.models import Settings

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

_TIMELINE_MONTH_CHOICES = (1, 3, 6)
_TIMELINE_CHART_LEFT = 20
_TIMELINE_CHART_WIDTH = 940
_TIMELINE_TOP_MARGIN = 40
_TIMELINE_LANE_HEIGHT = 110

_TIMELINE_KIND_CSS = {
    "income": "timeline-stop-income",
    "outgoing": "timeline-stop-outgoing",
    "oneoff": "timeline-stop-outgoing",
    "transfer": "timeline-stop-transfer",
}


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
        context["outgoings_pct"] = outgoings_percentage(summary.total_income, summary.total_outgoings)
        return context


def _accounts_context(mode: str, settings: Settings) -> dict[str, Any]:
    """Context for the accounts page/partial, shared with `log_variance`'s HTMX re-render.

    Each outgoing gets a `.variance` attribute (the current period's
    OutgoingVariance, or None) set directly on the prefetched instance —
    simpler than a template dict-lookup filter. Each pot-linked one-off gets
    `.pot_saved` / `.pot_covered` (total saved in the linked pot vs. its
    amount) so the accounts page can show a covered/uncovered badge.
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
    pot_saved = dict(PotEntry.objects.values_list("pot").annotate(total=Sum("actual_amount")))
    accounts = list(accounts)
    transfer_amounts = resolve_transfer_amounts(accounts, mode, period)
    for account in accounts:
        for outgoing in account.outgoings.all():
            outgoing.variance = variances.get(outgoing.id)
        for oneoff in account.one_off_outgoings.all():
            if oneoff.linked_pot_id:
                oneoff.pot_saved = pot_saved.get(oneoff.linked_pot_id, ZERO)
                oneoff.pot_covered = oneoff.pot_saved >= oneoff.amount
        for transfer in (*account.transfers_out.all(), *account.transfers_in.all()):
            transfer.effective_amount = transfer_amounts.get(transfer.id, ZERO)

    return {
        "mode": mode,
        "mode_choices": Settings.BudgetMode.choices,
        "account_summaries": [account_summary(a, mode, period, transfer_amounts) for a in accounts],
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


def _requested_months(request: HttpRequest) -> int:
    """Timeline horizon in months: `?months=` override (1/3/6), else 3."""
    raw = request.GET.get("months")
    try:
        months = int(raw)
    except (TypeError, ValueError):
        return 3
    return months if months in _TIMELINE_MONTH_CHOICES else 3


def _label_dy(slot: int) -> float:
    """Interleaved vertical offsets for stacked labels: above line, below
    line, further above, further below, ..."""
    level = slot // 2
    return (-12 - 14 * level) if slot % 2 == 0 else (24 + 14 * level)


def _assign_label_dys(labels: list[tuple[float, float]]) -> list[float]:
    """labels = ordered (center_x, width). Returns a dy per label, placing
    each in the first vertical slot that doesn't horizontally overlap an
    earlier label already occupying that slot. Same-day stops share an x, so
    without this every label after the first two rendered on top of each other.
    ponytail: dense same-day clusters stack tall and can overflow the lane
    height / bleed into the next lane; upgrade to leader lines or "+N" grouping
    if that becomes a real problem."""
    slot_xmax: list[float] = []  # last occupied right-edge per slot
    dys: list[float] = []
    for cx, w in labels:
        xmin, xmax = cx - w / 2, cx + w / 2
        for slot in range(len(slot_xmax) + 1):
            if slot == len(slot_xmax):
                slot_xmax.append(xmin - 1)  # new slot, always free
            if slot_xmax[slot] <= xmin:
                slot_xmax[slot] = xmax
                dys.append(_label_dy(slot))
                break
    return dys


def _timeline_svg(lanes: list[AccountLane], start: date, end: date, currency: str) -> dict[str, Any]:
    """Geometry for the timeline SVG: lane rows of positioned stops, cross-lane
    transfer connectors, and month-boundary axis ticks. Kept in the view (not
    services) since it's presentation, not domain logic."""
    total_days = (end - start).days or 1

    def x_for(d: date) -> float:
        return _TIMELINE_CHART_LEFT + (d - start).days / total_days * _TIMELINE_CHART_WIDTH

    axis_ticks = []
    year, month = start.year, start.month
    while date(year, month, 1) < end:
        month_start = date(year, month, 1)
        axis_ticks.append({"x": x_for(max(month_start, start)), "label": month_start.strftime("%b %Y")})
        year, month = _shift_month(year, month, 1)

    lane_rows = []
    connector_points: dict[tuple[int, date], list[tuple[float, float]]] = {}
    for index, lane in enumerate(lanes):
        y = _TIMELINE_TOP_MARGIN + index * _TIMELINE_LANE_HEIGHT + _TIMELINE_LANE_HEIGHT / 2
        stops = []
        hover_points = []
        label_positions = []  # (center_x, estimated_width), same order as stops
        for stop in lane.stops:
            cx = x_for(stop.date)
            balance_str = f"{stop.balance:.2f}"
            amount_str = f"{stop.amount:+.2f}"
            text = f"{stop.label} {currency}{amount_str}"
            label_positions.append((cx, len(text) * 5.5 + 4))
            stops.append(
                {
                    "x": cx,
                    "y": y,
                    "css": _TIMELINE_KIND_CSS[stop.kind],
                    "label": stop.label,
                    "date": stop.date,
                    "amount_str": amount_str,
                    "balance_str": balance_str,
                }
            )
            hover_points.append({"x": cx, "balance": balance_str, "date": stop.date.strftime("%d %b")})
            if stop.transfer_id is not None:
                connector_points.setdefault((stop.transfer_id, stop.date), []).append((cx, y))
        for stop, dy in zip(stops, _assign_label_dys(label_positions), strict=True):
            stop["dy"] = dy
        lane_rows.append(
            {
                "account": lane.account,
                "y": y,
                "name_y": y - _TIMELINE_LANE_HEIGHT / 2 + 18,
                "balance_y": y + _TIMELINE_LANE_HEIGHT / 2 - 10,
                "stops": stops,
                "end_balance_str": f"{lane.end_balance:.2f}",
                "hover_id": f"lane-hover-{index}",
                "hover_points": hover_points,
            }
        )

    connectors = []
    for points in connector_points.values():
        if len(points) == 2:
            (x, y1), (_, y2) = points
            connectors.append({"x": x, "y1": y1, "y2": y2})

    height = _TIMELINE_TOP_MARGIN + _TIMELINE_LANE_HEIGHT * len(lanes) + 20
    return {"width": 1000, "height": height, "lanes": lane_rows, "connectors": connectors, "axis_ticks": axis_ticks}


class TimelineView(TemplateView):
    def get_template_names(self) -> list[str]:
        return ["budget/_timeline.html"] if _is_partial_request(self.request) else ["budget/timeline.html"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        settings = Settings.get()
        account_ids = _requested_account_ids(self.request)
        months = _requested_months(self.request)

        current_period = active_period(settings.budget_mode, settings.budget_start_day)
        start = current_period.start
        end_year, end_month = _shift_month(start.year, start.month, months)
        end = _monthly_anchor(end_year, end_month, start.day)

        lanes = account_timelines(start, end, account_ids, mode=settings.budget_mode, period=current_period)

        context["svg"] = _timeline_svg(lanes, start, end, settings.currency)
        context["all_accounts"] = Account.objects.filter(is_active=True)
        context["selected_account_ids"] = account_ids
        context["months"] = months
        context["month_choices"] = _TIMELINE_MONTH_CHOICES
        context["currency"] = settings.currency
        context["window"] = Period(start, end)
        context["has_stops"] = any(lane.stops for lane in lanes)
        return context


def _flow_json(graph: FlowGraph) -> dict[str, Any]:
    """Shapes a FlowGraph into the {data, links} structure ECharts' sankey
    series expects. Kept in the view (not services) since it's presentation,
    not domain logic — mirrors `_timeline_svg`. Node/link `kind` strings are
    resolved to theme colours client-side (see flow.html's extra_js) so the
    chart follows the light/dark toggle without a server round-trip."""
    return {
        "data": [{"name": node.name, "kind": node.kind} for node in graph.nodes],
        "links": [
            {"source": link.source, "target": link.target, "value": float(link.value), "kind": link.kind}
            for link in graph.links
        ],
    }


class FlowView(TemplateView):
    def get_template_names(self) -> list[str]:
        return ["budget/_flow.html"] if _is_partial_request(self.request) else ["budget/flow.html"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        settings = Settings.get()
        account_ids = _requested_account_ids(self.request)
        period = active_period(settings.budget_mode, settings.budget_start_day)

        graph = budget_flow(settings.budget_mode, period, account_ids)

        context["flow_data"] = _flow_json(graph)
        context["all_accounts"] = Account.objects.filter(is_active=True)
        context["selected_account_ids"] = account_ids
        context["currency"] = settings.currency
        context["has_flows"] = bool(graph.links)
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


class _DatePrefillMixin:
    """Pre-fills a date field from `?date=YYYY-MM-DD`, e.g. from the calendar's "+"."""

    date_field = ""

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        date = parse_date(self.request.GET.get("date") or "")
        if date:
            initial[self.date_field] = date
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


class OneOffOutgoingCreateView(_DatePrefillMixin, _AccountScopedCreateMixin, _BudgetFormMixin, CreateView):
    model = OneOffOutgoing
    form_class = OneOffOutgoingForm
    title = "Add one-off outgoing"
    date_field = "due_date"


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


class PotCreateView(_DatePrefillMixin, _PotFormMixin, CreateView):
    model = Pot
    form_class = PotForm
    title = "Add pot"
    date_field = "target_date"

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


@require_POST
def accept_pot_contribution(request: HttpRequest, pot_id: int) -> HttpResponse:
    """Accept the engine-suggested per-period contribution for a behind pot.

    The amount is recomputed server-side via `pot_progress` rather than
    trusted from the request — it's a derived value, not user input.
    """
    pot = get_object_or_404(Pot, pk=pot_id)
    settings = Settings.get()
    period = active_period(settings.budget_mode, settings.budget_start_day)

    progress = pot_progress(pot, settings.budget_mode, period)
    pot.monthly_target = to_display(progress.per_period_needed)
    pot.save(update_fields=["monthly_target"])
    messages.success(request, f"Updated {pot.name}'s monthly target to {pot.monthly_target}.")

    return render(request, "budget/_pots.html", _pots_context(settings))
