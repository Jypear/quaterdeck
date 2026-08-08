"""Budget views: overview, per-account, and pot-progress pages."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, TemplateView, UpdateView

from budget.forms import (
    AccountForm,
    IncomeStreamForm,
    OneOffOutgoingForm,
    OutgoingCategoryForm,
    OutgoingForm,
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
    Pot,
    PotEntry,
    Transfer,
)
from budget.services import (
    ZERO,
    AccountLane,
    FlowGraph,
    Period,
    TimelineStop,
    _monthly_anchor,
    _shift_month,
    _yearly_due,
    account_summary,
    account_timelines,
    active_period,
    budget_flow,
    budget_summary,
    category_totals,
    outgoings_percentage,
    pot_progress,
    prefetched_accounts,
    resolve_transfer_amounts,
    scheduled_dates,
    to_display,
)
from core.models import Settings

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

_TIMELINE_CHART_LEFT = 20
_TIMELINE_CHART_WIDTH = 940
_TIMELINE_LANE_HEIGHT = 110
_TIMELINE_MAX_LABEL_SLOTS = 3  # caps stacked labels at ±38px, safely inside one lane's own SVG
_TIMELINE_MAX_MARKER_RADIUS = 10

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


def _requested_ids(request: HttpRequest, param: str) -> list[int] | None:
    """IDs selected via repeated `?<param>=` params (e.g. `accounts`, `categories`), or
    None for "all"."""
    raw_ids = request.GET.getlist(param)
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
        account_ids = _requested_ids(self.request, "accounts")
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


def _accounts_context(mode: str, settings: Settings, category_ids: list[int] | None = None) -> dict[str, Any]:
    """Context for the accounts page/partial.

    Each pot-linked one-off or outgoing gets `.pot_saved` / `.pot_covered`
    (total saved in the linked pot vs. its amount, `None` when unlinked) so
    the accounts page can show a covered/uncovered badge. Each yearly
    outgoing gets `.due_this_period` so the page can flag a bill that's
    actually due now, regardless of its `yearly_billing` mode. Each account
    gets `.filtered_outgoings` — its outgoings narrowed to `category_ids`
    (all of them when `category_ids` is None) — for the template to iterate
    instead of the full `outgoings.all()`.
    """
    period = active_period(mode, settings.budget_start_day)
    accounts = prefetched_accounts()
    pot_saved = dict(PotEntry.objects.values_list("pot").annotate(total=Sum("actual_amount")))
    pot_for_outgoing = dict(Pot.objects.filter(linked_outgoing__isnull=False).values_list("linked_outgoing_id", "id"))
    transfer_amounts = resolve_transfer_amounts(accounts, mode, period)
    for account in accounts:
        for outgoing in account.outgoings.all():
            pot_id = pot_for_outgoing.get(outgoing.id)
            outgoing.pot_covered = pot_saved.get(pot_id, ZERO) >= outgoing.amount if pot_id else None
            outgoing.pot_saved = pot_saved.get(pot_id, ZERO) if pot_id else None
            due = _yearly_due(outgoing, period.start) if outgoing.frequency == "yearly" else None
            outgoing.due_this_period = due is not None and due < period.end
        account.filtered_outgoings = (
            list(account.outgoings.all())
            if category_ids is None
            else [o for o in account.outgoings.all() if o.category_id in category_ids]
        )
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
        "category_totals": category_totals(accounts, mode, period, category_ids),
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
        category_ids = _requested_ids(self.request, "categories")
        context.update(_accounts_context(mode, settings, category_ids))
        context["selected_category_ids"] = category_ids
        if not _is_partial_request(self.request):
            context["categories"] = OutgoingCategory.objects.all()
        return context


class PotListView(TemplateView):
    template_name = "budget/pots.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(_pots_context(Settings.get()))
        return context


def _label_dy(slot: int) -> float:
    """Interleaved vertical offsets for stacked labels: above line, below
    line, further above, further below, ..."""
    level = slot // 2
    return (-12 - 14 * level) if slot % 2 == 0 else (24 + 14 * level)


def _assign_label_dys(labels: list[tuple[float, float]]) -> list[float | None]:
    """labels = ordered (center_x, width). Returns a dy per label, placing
    each in the first vertical slot (up to `_TIMELINE_MAX_LABEL_SLOTS`) that
    doesn't horizontally overlap an earlier label already occupying that
    slot. Same-day stops share an x, so without this every label after the
    first two rendered on top of each other.
    Labels that don't fit in any of the capped slots get `None` (no label
    rendered — the marker's count badge and the click-through detail panel
    carry the info instead), so a dense day can never stack tall enough to
    bleed into the lane above or below.
    ponytail: labels beyond the cap silently disappear rather than
    truncating/wrapping; revisit with leader lines if that turns out to
    hide something the count badge doesn't already convey."""
    slot_xmax: list[float] = []  # last occupied right-edge per slot
    dys: list[float | None] = []
    for cx, w in labels:
        xmin, xmax = cx - w / 2, cx + w / 2
        placed = False
        for slot in range(min(len(slot_xmax) + 1, _TIMELINE_MAX_LABEL_SLOTS)):
            if slot == len(slot_xmax):
                slot_xmax.append(xmin - 1)  # new slot, always free
            if slot_xmax[slot] <= xmin:
                slot_xmax[slot] = xmax
                dys.append(_label_dy(slot))
                placed = True
                break
        if not placed:
            dys.append(None)
    return dys


def _timeline_svg(lanes: list[AccountLane], start: date, end: date, currency: str) -> dict[str, Any]:
    """Geometry for the timeline: one small SVG per account (positioned
    markers on a single line) plus shared month-boundary axis ticks. Kept in
    the view (not services) since it's presentation, not domain logic.

    Each account gets its own SVG, rather than one tall SVG with a lane per
    account, so a clicked day's detail panel can sit directly under the
    account it belongs to instead of in one shared block below everything —
    that also means there's no single shared canvas left to draw cross-lane
    transfer connectors on; a transfer still shows as a coloured marker in
    both accounts on its date, just without the linking line.

    Stops are clustered per (account, date) into a single marker — same-day
    entries in one account would otherwise resolve to the same x and render
    as indistinguishable overlapping circles. A cluster's entries (for the
    click-through detail panel) are returned separately, keyed by marker id,
    since the SVG itself has no good way to hold a variable-length list.
    """
    total_days = (end - start).days or 1

    def x_for(d: date) -> float:
        return _TIMELINE_CHART_LEFT + (d - start).days / total_days * _TIMELINE_CHART_WIDTH

    axis_ticks = []
    year, month = start.year, start.month
    while date(year, month, 1) < end:
        month_start = date(year, month, 1)
        axis_ticks.append({"x": x_for(max(month_start, start)), "label": month_start.strftime("%b %Y")})
        year, month = _shift_month(year, month, 1)

    line_y = _TIMELINE_LANE_HEIGHT / 2
    lane_rows = []
    cluster_details: dict[str, dict[str, Any]] = {}
    for index, lane in enumerate(lanes):
        day_groups: dict[date, list[TimelineStop]] = {}
        for stop in lane.stops:
            day_groups.setdefault(stop.date, []).append(stop)

        clusters = []
        hover_points = []
        label_positions = []  # (center_x, estimated_width), same order as clusters
        for day_index, (d, day_stops) in enumerate(sorted(day_groups.items())):
            cx = x_for(d)
            count = len(day_stops)
            net = sum((s.amount for s in day_stops), ZERO)
            balance_str = f"{day_stops[-1].balance:.2f}"
            cluster_id = f"cl-{index}-{day_index}"
            if count == 1:
                css = _TIMELINE_KIND_CSS[day_stops[0].kind]
                label = f"{day_stops[0].label} {currency}{day_stops[0].amount:+.2f}"
            else:
                css = _TIMELINE_KIND_CSS["income"] if net >= 0 else _TIMELINE_KIND_CSS["outgoing"]
                label = f"{count} entries {currency}{net:+.2f}"
            label_positions.append((cx, len(label) * 5.5 + 4))
            clusters.append(
                {
                    "id": cluster_id,
                    "x": cx,
                    "y": line_y,
                    "r": 6 if count == 1 else min(6 + (count - 1) * 1.5, _TIMELINE_MAX_MARKER_RADIUS),
                    "count": count,
                    "css": css,
                    "label": label,
                    "date": d,
                    "balance_str": balance_str,
                }
            )
            hover_points.append({"x": cx, "balance": balance_str, "date": d.strftime("%d %b")})
            cluster_details[cluster_id] = {
                "account": lane.account.name,
                "date": d.strftime("%a %d %b %Y"),
                "balance_str": balance_str,
                "entries": [
                    {"label": s.label, "amount_str": f"{s.amount:+.2f}", "css": _TIMELINE_KIND_CSS[s.kind]}
                    for s in day_stops
                ],
            }
        for cluster, dy in zip(clusters, _assign_label_dys(label_positions), strict=True):
            cluster["label_dy"] = dy
        lane_rows.append(
            {
                "account": lane.account,
                "clusters": clusters,
                "end_balance_str": f"{lane.end_balance:.2f}",
                "hover_id": f"lane-hover-{index}",
                "hover_points": hover_points,
            }
        )

    return {
        "width": _TIMELINE_CHART_WIDTH + _TIMELINE_CHART_LEFT,
        "lane_height": _TIMELINE_LANE_HEIGHT,
        "line_y": line_y,
        "lanes": lane_rows,
        "axis_ticks": axis_ticks,
        "cluster_details": cluster_details,
    }


class TimelineView(TemplateView):
    def get_template_names(self) -> list[str]:
        return ["budget/_timeline.html"] if _is_partial_request(self.request) else ["budget/timeline.html"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        settings = Settings.get()
        account_ids = _requested_ids(self.request, "accounts")

        current_period = active_period(settings.budget_mode, settings.budget_start_day)
        start = current_period.start
        end_year, end_month = _shift_month(start.year, start.month, 1)
        end = _monthly_anchor(end_year, end_month, start.day)

        lanes = account_timelines(start, end, account_ids, mode=settings.budget_mode, period=current_period)

        context["svg"] = _timeline_svg(lanes, start, end, settings.currency)
        context["all_accounts"] = Account.objects.filter(is_active=True)
        context["selected_account_ids"] = account_ids
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
        account_ids = _requested_ids(self.request, "accounts")
        group_by_category = self.request.GET.get("group") == "category"
        period = active_period(settings.budget_mode, settings.budget_start_day)

        graph = budget_flow(settings.budget_mode, period, account_ids, group_by_category)

        context["flow_data"] = _flow_json(graph)
        context["all_accounts"] = Account.objects.filter(is_active=True)
        context["selected_account_ids"] = account_ids
        context["group_by_category"] = group_by_category
        context["currency"] = settings.currency
        context["has_flows"] = bool(graph.links)
        return context


# --- Detail views -----------------------------------------------------------


class _BudgetDetailMixin:
    """Shared currency/mode/period context for budget detail views."""

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        settings = Settings.get()
        mode = _requested_mode(self.request, settings)
        context["currency"] = settings.currency
        context["mode"] = mode
        context["period"] = active_period(mode, settings.budget_start_day)
        return context


def _next_dates(entry: Any, count: int = 6) -> list[date]:
    """The next `count` scheduled payment dates for a FrequencyMixin entry, from today."""
    today = date.today()
    return scheduled_dates(entry, today, today + timedelta(days=366))[:count]


class AccountDetailView(_BudgetDetailMixin, DetailView):
    model = Account
    template_name = "budget/account_detail.html"
    context_object_name = "account"
    queryset = Account.objects.prefetch_related(
        "income_streams",
        "outgoings__category",
        "transfers_in__from_account",
        "transfers_out__to_account",
        "one_off_outgoings__linked_pot",
    )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        mode, period = context["mode"], context["period"]
        transfer_amounts = resolve_transfer_amounts(prefetched_accounts(), mode, period)
        for transfer in (*self.object.transfers_out.all(), *self.object.transfers_in.all()):
            transfer.effective_amount = transfer_amounts.get(transfer.id, ZERO)
        context["summary"] = account_summary(self.object, mode, period, transfer_amounts)
        return context


class IncomeStreamDetailView(_BudgetDetailMixin, DetailView):
    model = IncomeStream
    template_name = "budget/income_detail.html"
    context_object_name = "income"
    queryset = IncomeStream.objects.select_related("account")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["upcoming_dates"] = _next_dates(self.object)
        return context


class OutgoingDetailView(_BudgetDetailMixin, DetailView):
    model = Outgoing
    template_name = "budget/outgoing_detail.html"
    context_object_name = "outgoing"
    queryset = Outgoing.objects.select_related("category", "account").prefetch_related("pots_linked")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["upcoming_dates"] = _next_dates(self.object)
        return context


class TransferDetailView(_BudgetDetailMixin, DetailView):
    model = Transfer
    template_name = "budget/transfer_detail.html"
    context_object_name = "transfer"
    queryset = Transfer.objects.select_related("from_account", "to_account")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        mode, period = context["mode"], context["period"]
        transfer_amounts = resolve_transfer_amounts(prefetched_accounts(), mode, period)
        context["effective_amount"] = transfer_amounts.get(self.object.id, ZERO)
        context["upcoming_dates"] = _next_dates(self.object)
        return context


class OneOffOutgoingDetailView(_BudgetDetailMixin, DetailView):
    model = OneOffOutgoing
    template_name = "budget/oneoff_detail.html"
    context_object_name = "oneoff"
    queryset = OneOffOutgoing.objects.select_related("account", "linked_pot")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        if self.object.linked_pot_id:
            saved = self.object.linked_pot.entries.aggregate(total=Sum("actual_amount"))["total"] or ZERO
            context["pot_saved"] = saved
            context["pot_covered"] = saved >= self.object.amount
        return context


class PotDetailView(_BudgetDetailMixin, DetailView):
    model = Pot
    template_name = "budget/pot_detail.html"
    context_object_name = "pot"
    queryset = Pot.objects.select_related("linked_project", "linked_one_off", "linked_outgoing").prefetch_related(
        "entries"
    )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["progress"] = pot_progress(self.object, context["mode"], context["period"])
        context["entries"] = self.object.entries.all()
        return context


# --- Account / IncomeStream / Outgoing CRUD --------------------------------
#
# Plain full-page forms + redirect, not HTMX modals — smallest correct CRUD.
# ponytail: full-page CBV CRUD, HTMX modals if inline editing is wanted later.


class _BudgetFormMixin:
    """Shared template + page title + success message for CRUD views.

    No success_url — the model's get_absolute_url() sends Create/Update
    straight to its detail page (mirrors ProjectDetailView's pattern).
    Models without a detail page (OutgoingCategory) set success_url explicitly.
    """

    template_name = "budget/_form.html"
    cancel_url = reverse_lazy("budget:accounts")
    success_message = "Saved."
    title = ""

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("title", self.title)
        context.setdefault("cancel_url", self.cancel_url)
        return context

    def form_valid(self, form: Any) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response


class _PotFormMixin(_BudgetFormMixin):
    """Same as `_BudgetFormMixin` but redirects to the pot's detail page.

    Honors `?next=` (e.g. a project's detail page) so pots created/edited
    from that context return there instead of always landing on the detail page.
    """

    cancel_url = reverse_lazy("budget:pots")

    def get_success_url(self) -> str:
        next_url = self.request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()
        ):
            return next_url
        return super().get_success_url()

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
    """No detail page for categories — success_url is explicit since there's
    no get_absolute_url() for ModelFormMixin to fall back to."""

    model = OutgoingCategory
    form_class = OutgoingCategoryForm
    success_url = reverse_lazy("budget:accounts")
    title = "Add category"


class OutgoingCategoryUpdateView(_BudgetFormMixin, UpdateView):
    model = OutgoingCategory
    form_class = OutgoingCategoryForm
    success_url = reverse_lazy("budget:accounts")
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


# --- Feedback-loop logging: actual saved -------------------------------------
#
# Keys on (pot, period_start=active period) via update_or_create, so
# re-submitting for the same period overwrites — that's also the correction
# path, no separate edit UI needed.


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
