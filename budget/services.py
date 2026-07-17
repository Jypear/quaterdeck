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
        # ponytail: yearly has no month field to place a day-of-month within
        # the year, so it can't be scheduled yet. Add `recurring_month` if needed.
        return []

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


def account_summary(account: Account, mode: str, period: Period) -> AccountSummary:
    """Normalised income/outgoings/transfers for one account over `period`.

    Expects `account`'s related managers to already be prefetched by the
    caller (income_streams, outgoings, transfers_in, transfers_out,
    one_off_outgoings) to avoid N+1 queries across many accounts.
    """
    income = sum((normalise(i.amount, i.frequency, mode) for i in account.income_streams.all()), ZERO)
    outgoings = sum((normalise(o.amount, o.frequency, mode) for o in account.outgoings.all()), ZERO)
    transfers_in = sum((normalise(t.amount, t.frequency, mode) for t in account.transfers_in.all()), ZERO)
    transfers_out = sum((normalise(t.amount, t.frequency, mode) for t in account.transfers_out.all()), ZERO)
    one_offs = sum(
        (o.amount for o in account.one_off_outgoings.all() if period.start <= o.due_date < period.end),
        ZERO,
    )
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


def _prefetched_accounts(account_ids: Iterable[int] | None) -> list[Account]:
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
    figure.
    """
    accounts = _prefetched_accounts(account_ids)
    summaries = [account_summary(a, mode, period) for a in accounts]

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
    )


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


def account_timelines(start: date, end: date, account_ids: Iterable[int] | None = None) -> list[AccountLane]:
    """One lane per active (or selected) account: every dated
    income/outgoing/transfer/one-off in [start, end), in date order, with a
    running balance from 0.

    Recurring entries use `scheduled_dates` (unscheduled entries, i.e. no
    `recurring_day`, don't appear — nothing to place them on the axis).
    """
    lanes = []
    for account in _prefetched_accounts(account_ids):
        raw: list[tuple[date, str, Decimal, str, int | None]] = []
        for income in account.income_streams.all():
            for d in scheduled_dates(income, start, end):
                raw.append((d, income.name, income.amount, "income", None))
        for outgoing in account.outgoings.all():
            for d in scheduled_dates(outgoing, start, end):
                raw.append((d, outgoing.name, -outgoing.amount, "outgoing", None))
        for transfer in account.transfers_out.all():
            for d in scheduled_dates(transfer, start, end):
                raw.append((d, transfer.name, -transfer.amount, "transfer", transfer.id))
        for transfer in account.transfers_in.all():
            for d in scheduled_dates(transfer, start, end):
                raw.append((d, transfer.name, transfer.amount, "transfer", transfer.id))
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
