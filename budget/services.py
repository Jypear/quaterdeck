"""Budget engine: period windows, frequency normalisation, and summaries.

Pure functions only — no HTTP, no template concerns. Views call into this
module and pass the results straight to templates.

All money math uses `Decimal`. Intermediate calculations keep full precision;
`to_display()` is the only place amounts get quantized to 2 decimal places,
so callers should normalise/sum first and only round at the display edge.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, NamedTuple

from budget.models import Account, IncomeStream, Outgoing, OutgoingVariance, Pot, PotEntry, Transfer
from core.models import Settings

if TYPE_CHECKING:
    from collections.abc import Iterable

    RecurringEntry = IncomeStream | Outgoing | Transfer

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0")

# Periods per year for each frequency/mode, used to convert any amount to an
# annual figure and back down into the target period.
_PERIODS_PER_YEAR: dict[str, Decimal] = {
    Settings.BudgetMode.WEEKLY: Decimal(52),
    Settings.BudgetMode.MONTHLY: Decimal(12),
    Settings.BudgetMode.YEARLY: Decimal(1),
}


def to_display(amount: Decimal) -> Decimal:
    """Round an amount to 2dp for display. Never use mid-calculation."""
    return amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def outgoings_percentage(income: Decimal, outgoings: Decimal) -> int:
    """Outgoings as a percentage of income, capped at 100 for progress bars/gauges."""
    if income <= 0:
        return 100 if outgoings > 0 else 0
    return min(100, int(outgoings / income * 100))


def normalise(amount: Decimal, frequency: str, mode: str) -> Decimal:
    """Convert `amount` (recurring at `frequency`) into its equivalent over one `mode` period."""
    annual = amount * _PERIODS_PER_YEAR[frequency]
    return annual / _PERIODS_PER_YEAR[mode]


class Period(NamedTuple):
    start: date
    end: date


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return (year, month) shifted by `delta` months (1-indexed month)."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _monthly_anchor(year: int, month: int, day: int) -> date:
    """The budget-window anchor date for `year`/`month`, clamping `day` to the month's length."""

    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _weekend_adjusted(d: date, adjust: str) -> date:
    """Shift `d` off a weekend per `adjust` ("before"/"after"/""). No-op on weekdays."""
    if d.isoweekday() < 6 or not adjust:
        return d
    if adjust == "before":
        return d - timedelta(days=d.isoweekday() - 5)  # Sat(6)->Fri, Sun(7)->Fri
    return d + timedelta(days=8 - d.isoweekday())  # Sat(6)->Mon, Sun(7)->Mon


def scheduled_dates(entry: RecurringEntry, start: date, end: date) -> list[date]:
    """Actual payment dates for a recurring entry (anything with `FrequencyMixin`
    fields) within the half-open [start, end) range. Empty if unscheduled.

    Display/calendar placement only — does not feed budget totals.
    """
    if entry.recurring_day is None:
        return []

    if entry.frequency == "weekly":
        return [d for d in _daterange(start, end) if _is_weekly_occurrence(d, entry)]

    if entry.frequency == "yearly":
        if entry.recurring_month is None:
            return []
        dates = []
        for year in range(start.year, end.year + 1):
            anchor = _weekend_adjusted(
                _monthly_anchor(year, entry.recurring_month, entry.recurring_day), entry.weekend_adjust
            )
            if start <= anchor < end:
                dates.append(anchor)
        return dates

    # monthly
    dates = []
    year, month = start.year, start.month
    while date(year, month, 1) < end:
        anchor = _weekend_adjusted(_monthly_anchor(year, month, entry.recurring_day), entry.weekend_adjust)
        if start <= anchor < end:
            dates.append(anchor)
        year, month = _shift_month(year, month, 1)
    return dates


def _is_weekly_occurrence(d: date, entry: RecurringEntry) -> bool:
    if d.isoweekday() != entry.recurring_day:
        return False
    if not entry.week_interval or entry.week_interval <= 1 or entry.week_anchor is None:
        return True
    return (d - entry.week_anchor).days % (7 * entry.week_interval) == 0


def _daterange(start: date, end: date) -> Iterable[date]:
    d = start
    while d < end:
        yield d
        d += timedelta(days=1)


def active_period(mode: str, start_day: int, today: date | None = None) -> Period:
    """The budget period (half-open [start, end)) that `today` falls within, for `mode`.

    `start_day` is an ISO weekday (1-7) in weekly mode, or a day-of-month
    (1-31, clamped to short months) in monthly/yearly mode. Yearly mode
    anchors on 1 January (the model has no start-month field).

    `mode` is passed explicitly (rather than reading `Settings.budget_mode`
    directly) so callers can compute the period for a display-only mode
    override without that override needing to touch stored Settings.
    """
    today = today or date.today()

    if mode == Settings.BudgetMode.WEEKLY:
        offset = (today.isoweekday() - start_day) % 7
        start = today - timedelta(days=offset)
        return Period(start, start + timedelta(days=7))

    if mode == Settings.BudgetMode.YEARLY:
        this_year_start = _monthly_anchor(today.year, 1, start_day)
        if today >= this_year_start:
            return Period(this_year_start, _monthly_anchor(today.year + 1, 1, start_day))
        return Period(_monthly_anchor(today.year - 1, 1, start_day), this_year_start)

    # monthly
    this_month_start = _monthly_anchor(today.year, today.month, start_day)
    if today >= this_month_start:
        next_year, next_month = _shift_month(today.year, today.month, 1)
        return Period(this_month_start, _monthly_anchor(next_year, next_month, start_day))
    prev_year, prev_month = _shift_month(today.year, today.month, -1)
    return Period(_monthly_anchor(prev_year, prev_month, start_day), this_month_start)


def periods_between(start: date, end: date, mode: str) -> int:
    """Whole `mode`-length periods between `start` and `end`, minimum 1."""
    if end <= start:
        return 1
    if mode == Settings.BudgetMode.WEEKLY:
        days = (end - start).days
        return max(1, -(-days // 7))
    if mode == Settings.BudgetMode.YEARLY:
        years = end.year - start.year
        if (end.month, end.day) < (start.month, start.day):
            years -= 1
        return max(1, years)
    # monthly
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(1, months)


def _yearly_due(entry: Outgoing, on_or_after: date) -> date | None:
    """The next occurrence of `entry`'s yearly month/day on or after `on_or_after`,
    or None if unscheduled (no day or month set)."""
    if entry.recurring_day is None or entry.recurring_month is None:
        return None
    anchor = _weekend_adjusted(
        _monthly_anchor(on_or_after.year, entry.recurring_month, entry.recurring_day), entry.weekend_adjust
    )
    if anchor >= on_or_after:
        return anchor
    return _weekend_adjusted(
        _monthly_anchor(on_or_after.year + 1, entry.recurring_month, entry.recurring_day), entry.weekend_adjust
    )


def outgoing_amount(outgoing: Outgoing, mode: str, period: Period) -> Decimal:
    """The per-`period` amount for a recurring `Outgoing`.

    Non-yearly entries, and yearly entries left on the default `spread` billing,
    are just `normalise(amount, frequency, mode)` — today's flat-amortised figure.
    `spread_to_due` divides the amount across the periods remaining until the next
    due date; `due_period` charges the full amount in the period containing that due
    date and nothing elsewhere. An unscheduled yearly entry (no day/month set) falls
    back to `spread` rather than silently dropping the amount.
    """
    spread = normalise(outgoing.amount, outgoing.frequency, mode)
    if outgoing.frequency != "yearly" or outgoing.yearly_billing == Outgoing.YearlyBilling.SPREAD:
        return spread

    due = _yearly_due(outgoing, period.start)
    if due is None:
        return spread

    if outgoing.yearly_billing == Outgoing.YearlyBilling.DUE_PERIOD:
        return outgoing.amount if due < period.end else ZERO

    # spread_to_due
    return outgoing.amount / periods_between(period.start, due, mode)


def _account_income(account: Account, mode: str) -> Decimal:
    return sum((normalise(i.amount, i.frequency, mode) for i in account.income_streams.all()), ZERO)


def _account_outgoings(account: Account, mode: str, period: Period) -> Decimal:
    return sum((outgoing_amount(o, mode, period) for o in account.outgoings.all()), ZERO)


def _account_one_offs(account: Account, period: Period) -> Decimal:
    return sum(
        (o.amount for o in account.one_off_outgoings.all() if period.start <= o.due_date < period.end),
        ZERO,
    )


def _account_disposable(
    account: Account,
    mode: str,
    period: Period,
    amounts: dict[int, Decimal],
    exclude_transfer_id: int,
) -> Decimal:
    """`account`'s income/outgoings/one-offs net, plus every already-resolved
    transfer touching it except `exclude_transfer_id` — i.e. what's left in
    the account before that one transfer is applied. Shared by the `split`
    weighting (excludes the split transfer itself, not yet resolved) and the
    `surplus` sweep (excludes the surplus transfer itself)."""
    other_in = sum((amounts.get(t.id, ZERO) for t in account.transfers_in.all()), ZERO)
    other_out = sum((amounts.get(t.id, ZERO) for t in account.transfers_out.all() if t.id != exclude_transfer_id), ZERO)
    return (
        _account_income(account, mode)
        + other_in
        - _account_outgoings(account, mode, period)
        - other_out
        - _account_one_offs(account, period)
    )


def resolve_transfer_amounts(accounts: Iterable[Account], mode: str, period: Period) -> dict[int, Decimal]:
    """Effective per-`period` amount for every transfer out of `accounts`.

    - fixed:   `normalise(amount, frequency, mode)`, same as a plain outgoing.
    - split:   this transfer's share of `to_account`'s funding need (its
               outgoings + fixed transfers-out + one-offs, minus its own
               income), weighted by each contributor's own disposable income
               (`_account_disposable` — income minus their own outgoings and
               other transfers) rather than raw salary:
               `share = required/n + (disposable - mean_disposable)`. This is
               what makes two contributors' post-split remainders come out
               equal even when their personal outgoings differ (see the
               `DynamicTransferTests.test_split_equalises_take_home_when_personal_outgoings_differ`
               regression) — weighting by raw salary alone would leave a gap
               equal to the difference in personal outgoings.
    - surplus: whatever's left in `from_account` after everything else
               (`_account_disposable` again, clamped to zero).

    All results clamp to zero (never surface a negative transfer). Resolved in
    dependency order fixed -> split -> surplus, so each stage can use amounts
    already resolved by the stages before it.

    Expects the same related-manager prefetch as `account_summary`. `accounts`
    should include both ends of every transfer of interest — a transfer
    reaching outside the set resolves using whatever prefetched data exists
    for its far end, falling back to zero if that account wasn't fetched.

    # ponytail: a destination's "required" only counts its FIXED transfers-out
    # (a split/surplus outflow would make the dependency circular), and a
    # surplus transfer only nets already-resolved siblings, so two surplus
    # transfers off one account both claim from the same remainder rather
    # than splitting it. Both match the one-savings-transfer,
    # one-split-pair, one-surplus-sweep household setup this was built for;
    # extend if a multi-hop chain of dynamic transfers is ever needed.
    """
    by_id = {a.id: a for a in accounts}
    all_transfers: list[Transfer] = [t for a in accounts for t in a.transfers_out.all()]
    amounts: dict[int, Decimal] = {}

    for transfer in all_transfers:
        if transfer.calc_method == Transfer.CalcMethod.FIXED:
            amounts[transfer.id] = normalise(transfer.amount or ZERO, transfer.frequency, mode)

    by_destination: dict[int, list[Transfer]] = {}
    for transfer in all_transfers:
        if transfer.calc_method == Transfer.CalcMethod.SPLIT:
            by_destination.setdefault(transfer.to_account_id, []).append(transfer)

    for dest_id, group in by_destination.items():
        dest = by_id.get(dest_id)
        if dest is None:
            for transfer in group:
                amounts[transfer.id] = ZERO
            continue

        required = (
            _account_outgoings(dest, mode, period)
            + _account_one_offs(dest, period)
            + sum(
                (amounts[t.id] for t in dest.transfers_out.all() if t.calc_method == Transfer.CalcMethod.FIXED),
                ZERO,
            )
            - _account_income(dest, mode)
        )
        required = max(ZERO, required)

        disposables = {
            t.id: (
                _account_disposable(by_id[t.from_account_id], mode, period, amounts, t.id)
                if t.from_account_id in by_id
                else ZERO
            )
            for t in group
        }
        mean_disposable = sum(disposables.values(), ZERO) / len(group)
        share = required / len(group)
        for transfer in group:
            amounts[transfer.id] = max(ZERO, share + (disposables[transfer.id] - mean_disposable))

    for transfer in all_transfers:
        if transfer.calc_method != Transfer.CalcMethod.SURPLUS:
            continue
        source = by_id.get(transfer.from_account_id)
        if source is None:
            amounts[transfer.id] = ZERO
            continue
        amounts[transfer.id] = max(ZERO, _account_disposable(source, mode, period, amounts, transfer.id))

    return amounts


@dataclass
class AccountSummary:
    account: Account
    income: Decimal
    outgoings: Decimal
    transfers_in: Decimal
    transfers_out: Decimal
    one_offs: Decimal
    net: Decimal
    covered: bool


def account_summary(
    account: Account,
    mode: str,
    period: Period,
    transfer_amounts: dict[int, Decimal] | None = None,
) -> AccountSummary:
    """Normalised income/outgoings/transfers for one account over `period`.

    `transfer_amounts` (from `resolve_transfer_amounts`) supplies each
    transfer's effective amount; omit it to fall back to a plain
    `normalise(amount, frequency, mode)` per transfer (fixed-only, no
    split/surplus support — kept for callers that only ever use fixed
    transfers, e.g. existing tests).

    Expects `account`'s related managers to already be prefetched by the
    caller (income_streams, outgoings, transfers_in, transfers_out,
    one_off_outgoings) to avoid N+1 queries across many accounts.
    """
    income = _account_income(account, mode)
    outgoings = _account_outgoings(account, mode, period)
    if transfer_amounts is None:
        transfers_in = sum((normalise(t.amount or ZERO, t.frequency, mode) for t in account.transfers_in.all()), ZERO)
        transfers_out = sum((normalise(t.amount or ZERO, t.frequency, mode) for t in account.transfers_out.all()), ZERO)
    else:
        transfers_in = sum((transfer_amounts.get(t.id, ZERO) for t in account.transfers_in.all()), ZERO)
        transfers_out = sum((transfer_amounts.get(t.id, ZERO) for t in account.transfers_out.all()), ZERO)
    one_offs = _account_one_offs(account, period)
    net = income + transfers_in - outgoings - transfers_out - one_offs
    return AccountSummary(
        account=account,
        income=income,
        outgoings=outgoings,
        transfers_in=transfers_in,
        transfers_out=transfers_out,
        one_offs=one_offs,
        net=net,
        covered=net >= 0,
    )


@dataclass
class BudgetSummary:
    mode: str
    period: Period
    accounts: list[AccountSummary] = field(default_factory=list)
    total_income: Decimal = ZERO
    total_outgoings: Decimal = ZERO
    surplus: Decimal = ZERO
    variance_total: Decimal = ZERO
    one_off_total: Decimal = ZERO
    adjusted_surplus: Decimal = ZERO
    pot_contributions: Decimal = ZERO
    unallocated_surplus: Decimal = ZERO
    yearly_due: list[Outgoing] = field(default_factory=list)


def prefetched_accounts(account_ids: Iterable[int] | None = None) -> list[Account]:
    queryset = Account.objects.filter(is_active=True).prefetch_related(
        "income_streams",
        "outgoings",
        "transfers_in",
        "transfers_out",
        "one_off_outgoings",
    )
    if account_ids is not None:
        queryset = queryset.filter(id__in=account_ids)
    return list(queryset)


def budget_summary(mode: str, period: Period, account_ids: Iterable[int] | None = None) -> BudgetSummary:
    """Totals across the selected (or all active) accounts for `period`.

    `surplus` is income minus outgoings only (transfers net to zero once all
    accounts are included). `adjusted_surplus` further deducts this period's
    outgoing variances and one-off payments. `unallocated_surplus` deducts
    what's already been logged into pots this period — the nudge-to-allocate
    figure. `yearly_due` lists every yearly outgoing whose due date falls in
    `period` regardless of its `yearly_billing` mode — a `spread` bill is
    still worth flagging as actually due, even though its amount doesn't
    spike.
    """
    accounts = prefetched_accounts(account_ids)
    transfer_amounts = resolve_transfer_amounts(accounts, mode, period)
    summaries = [account_summary(a, mode, period, transfer_amounts) for a in accounts]

    total_income = sum((s.income for s in summaries), ZERO)
    total_outgoings = sum((s.outgoings for s in summaries), ZERO)
    surplus = total_income - total_outgoings

    variance_total = sum(
        (
            v.delta
            for v in OutgoingVariance.objects.filter(
                outgoing__account__in=accounts,
                period_start__gte=period.start,
                period_start__lt=period.end,
            ).select_related("outgoing")
        ),
        ZERO,
    )
    one_off_total = sum((s.one_offs for s in summaries), ZERO)
    adjusted_surplus = surplus - variance_total - one_off_total

    pot_contributions = sum(
        (e.actual_amount for e in PotEntry.objects.filter(period_start__gte=period.start, period_start__lt=period.end)),
        ZERO,
    )
    unallocated_surplus = adjusted_surplus - pot_contributions

    yearly_due = [
        o
        for a in accounts
        for o in a.outgoings.all()
        if o.frequency == "yearly" and (due := _yearly_due(o, period.start)) is not None and due < period.end
    ]

    return BudgetSummary(
        mode=mode,
        period=period,
        accounts=summaries,
        total_income=total_income,
        total_outgoings=total_outgoings,
        surplus=surplus,
        variance_total=variance_total,
        one_off_total=one_off_total,
        adjusted_surplus=adjusted_surplus,
        pot_contributions=pot_contributions,
        unallocated_surplus=unallocated_surplus,
        yearly_due=yearly_due,
    )


@dataclass
class FlowNode:
    name: str  # unique among all nodes — the presentation layer keys ECharts sankey nodes by name
    kind: str  # "income" / "account" / "bill" / "surplus" / "pot" / "unallocated"


@dataclass
class FlowLink:
    source: str
    target: str
    value: Decimal
    kind: str  # "income" / "bill" / "transfer" / "surplus" / "pot" / "unallocated" — drives link colour


@dataclass
class FlowGraph:
    nodes: list[FlowNode] = field(default_factory=list)
    links: list[FlowLink] = field(default_factory=list)


def budget_flow(mode: str, period: Period, account_ids: Iterable[int] | None = None) -> FlowGraph:
    """Sankey-shaped view of one period's money movement: income -> accounts
    -> bills/one-offs, netted transfers between accounts, and each account's
    surplus pooled into a "Surplus" node that fans out to pot contributions
    and whatever's left ("Unallocated").

    Node names must be unique (see `FlowNode`); collisions (e.g. two bills
    both named "Insurance") get a disambiguating " (2)" suffix.

    Overspent accounts (net <= 0) contribute no surplus link — there's
    nothing to flow onward. Transfers to/from an account outside the
    selected set are skipped, since there'd be no node for them to land on.
    # ponytail: both are fine for a personal single-instance app; revisit if
    # the account filter needs to show partial/one-sided transfers.
    """
    accounts = prefetched_accounts(account_ids)
    included_ids = {a.id for a in accounts}
    transfer_amounts = resolve_transfer_amounts(accounts, mode, period)
    seen_names: dict[str, int] = {}
    nodes: list[FlowNode] = []
    links: list[FlowLink] = []

    def add_node(name: str, kind: str) -> str:
        seen_names[name] = seen_names.get(name, 0) + 1
        unique_name = name if seen_names[name] == 1 else f"{name} ({seen_names[name]})"
        nodes.append(FlowNode(unique_name, kind))
        return unique_name

    def add_link(source: str, target: str, value: Decimal, kind: str) -> None:
        if value > 0:
            links.append(FlowLink(source, target, value, kind))

    account_names = {a.id: add_node(a.name, "account") for a in accounts}

    transfers_in_total: dict[int, Decimal] = {}
    transfers_out_total: dict[int, Decimal] = {}
    net_transfers: dict[tuple[int, int], Decimal] = {}

    for account in accounts:
        for income in account.income_streams.all():
            amount = normalise(income.amount, income.frequency, mode)
            add_link(add_node(income.name, "income"), account_names[account.id], amount, "income")

        for outgoing in account.outgoings.all():
            amount = outgoing_amount(outgoing, mode, period)
            add_link(account_names[account.id], add_node(outgoing.name, "bill"), amount, "bill")

        for one_off in account.one_off_outgoings.all():
            if period.start <= one_off.due_date < period.end:
                add_link(account_names[account.id], add_node(one_off.name, "bill"), one_off.amount, "bill")

        for transfer in account.transfers_out.all():
            if transfer.to_account_id not in included_ids:
                continue
            amount = transfer_amounts.get(transfer.id, ZERO)
            transfers_out_total[account.id] = transfers_out_total.get(account.id, ZERO) + amount
            transfers_in_total[transfer.to_account_id] = transfers_in_total.get(transfer.to_account_id, ZERO) + amount
            pair = (min(account.id, transfer.to_account_id), max(account.id, transfer.to_account_id))
            signed = amount if account.id == pair[0] else -amount
            net_transfers[pair] = net_transfers.get(pair, ZERO) + signed

    # One netted link per account pair — avoids a 2-node cycle, which ECharts'
    # sankey (a DAG layout) can't render.
    for (low_id, high_id), signed in net_transfers.items():
        if signed > 0:
            add_link(account_names[low_id], account_names[high_id], signed, "transfer")
        elif signed < 0:
            add_link(account_names[high_id], account_names[low_id], -signed, "transfer")

    account_surplus: dict[int, Decimal] = {}
    for account in accounts:
        income = _account_income(account, mode)
        outgoings = _account_outgoings(account, mode, period)
        one_offs = _account_one_offs(account, period)
        net = (
            income
            + transfers_in_total.get(account.id, ZERO)
            - outgoings
            - transfers_out_total.get(account.id, ZERO)
            - one_offs
        )
        if net > 0:
            account_surplus[account.id] = net

    total_surplus = sum(account_surplus.values(), ZERO)
    if total_surplus > 0:
        surplus_name = add_node("Surplus", "surplus")
        for account_id, net in account_surplus.items():
            add_link(account_names[account_id], surplus_name, net, "surplus")

        pot_contributions = ZERO
        for entry in PotEntry.objects.filter(
            period_start__gte=period.start, period_start__lt=period.end
        ).select_related("pot"):
            add_link(surplus_name, add_node(entry.pot.name, "pot"), entry.actual_amount, "pot")
            pot_contributions += entry.actual_amount

        unallocated = total_surplus - pot_contributions
        if unallocated > 0:
            add_link(surplus_name, add_node("Unallocated", "unallocated"), unallocated, "unallocated")

    return FlowGraph(nodes=nodes, links=links)


@dataclass
class TimelineStop:
    date: date
    label: str
    amount: Decimal  # signed: + income/transfer-in, - outgoing/transfer-out/one-off
    kind: str  # "income" / "outgoing" / "transfer" / "oneoff"
    balance: Decimal  # running balance after this stop, starting from 0
    transfer_id: int | None = None  # shared by a transfer's two stops (out + in), for drawing a connector


@dataclass
class AccountLane:
    account: Account
    stops: list[TimelineStop]
    end_balance: Decimal


def account_timelines(
    start: date,
    end: date,
    account_ids: Iterable[int] | None = None,
    mode: str | None = None,
    period: Period | None = None,
) -> list[AccountLane]:
    """One lane per active (or selected) account: every dated
    income/outgoing/transfer/one-off in [start, end), in date order, with a
    running balance from 0.

    Recurring entries use `scheduled_dates` (unscheduled entries, i.e. no
    `recurring_day`, don't appear — nothing to place them on the axis).

    Pass `mode`/`period` (the current active budget period, not necessarily
    `[start, end)` — this window can span several periods) to resolve
    split/surplus transfers via `resolve_transfer_amounts`; without them,
    every transfer occurrence falls back to its raw `amount` (zero for
    split/surplus, since they have none).
    # ponytail: a dynamic transfer shows the *current* period's resolved
    # amount on every occurrence in the window, even ones in a different
    # period — fine for a display-only timeline; revisit if per-occurrence
    # resolution is needed for one-off-heavy months.
    """
    accounts = prefetched_accounts(account_ids)
    transfer_amounts = resolve_transfer_amounts(accounts, mode, period) if mode and period else {}

    lanes = []
    for account in accounts:
        raw: list[tuple[date, str, Decimal, str, int | None]] = []
        for income in account.income_streams.all():
            for d in scheduled_dates(income, start, end):
                raw.append((d, income.name, income.amount, "income", None))
        for outgoing in account.outgoings.all():
            for d in scheduled_dates(outgoing, start, end):
                raw.append((d, outgoing.name, -outgoing.amount, "outgoing", None))
        for transfer in account.transfers_out.all():
            amount = transfer_amounts.get(transfer.id, transfer.amount or ZERO)
            for d in scheduled_dates(transfer, start, end):
                raw.append((d, transfer.name, -amount, "transfer", transfer.id))
        for transfer in account.transfers_in.all():
            amount = transfer_amounts.get(transfer.id, transfer.amount or ZERO)
            for d in scheduled_dates(transfer, start, end):
                raw.append((d, transfer.name, amount, "transfer", transfer.id))
        for one_off in account.one_off_outgoings.all():
            if start <= one_off.due_date < end:
                raw.append((one_off.due_date, one_off.name, -one_off.amount, "oneoff", None))

        raw.sort(key=lambda row: row[0])
        stops = []
        balance = ZERO
        for d, label, amount, kind, transfer_id in raw:
            balance += amount
            stops.append(TimelineStop(d, label, amount, kind, balance, transfer_id))

        lanes.append(AccountLane(account=account, stops=stops, end_balance=balance))
    return lanes


@dataclass
class PotProgress:
    pot: Pot
    status: str  # "ahead" / "on_track" / "behind"
    saved_to_date: Decimal
    expected_to_date: Decimal
    periods_elapsed: int
    remaining_periods: int
    per_period_needed: Decimal


def pot_progress(pot: Pot, mode: str, period: Period) -> PotProgress:
    """On-track/behind/ahead status for `pot` as of `period`, plus the
    per-remaining-period contribution needed to still hit `target_date`.

    Each `PotEntry` represents one logged contribution period, so
    `periods_elapsed` is simply the count of entries up to and including
    `period` — this counts periods the user has actually logged, not
    calendar time, since Pot has no creation date to measure from.
    """
    entries = list(pot.entries.filter(period_start__lte=period.start))
    saved_to_date = sum((e.actual_amount for e in entries), ZERO)
    periods_elapsed = len(entries)
    expected_to_date = pot.monthly_target * periods_elapsed

    if saved_to_date > expected_to_date:
        status = "ahead"
    elif saved_to_date < expected_to_date:
        status = "behind"
    else:
        status = "on_track"

    remaining_periods = periods_between(period.start, pot.target_date, mode)
    remaining_amount = pot.target_amount - saved_to_date
    per_period_needed = remaining_amount / remaining_periods if remaining_amount > 0 else ZERO

    return PotProgress(
        pot=pot,
        status=status,
        saved_to_date=saved_to_date,
        expected_to_date=expected_to_date,
        periods_elapsed=periods_elapsed,
        remaining_periods=remaining_periods,
        per_period_needed=per_period_needed,
    )
