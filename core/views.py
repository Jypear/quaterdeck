"""Core views — dashboard, calendar, and settings."""

from __future__ import annotations

import calendar as calendar_module
import secrets
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView, UpdateView

from budget.forms import IncomeAmountForm
from budget.models import IncomeStream, Pot
from budget.services import (
    AccountSummary,
    active_period,
    budget_summary,
    outgoings_percentage,
    pot_progress,
    prefetched_accounts,
    transfer_plan,
    upcoming_yearly_bills,
)
from core.events import CalEvent, month_events
from core.forms import SettingsForm
from core.models import Settings
from notes.models import Note
from projects.models import Project
from tasks.models import Task

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


def _account_chart_data(account_summaries: list[AccountSummary]) -> dict[str, Any]:
    """Net (income + transfers in, minus outgoings + transfers out + one-offs)
    per account, biggest surplus first — a single diverging bar per account
    rather than an in/out pair, so the dashboard chart answers "which
    accounts are short" at a glance instead of needing gridlines read off
    two bars. Mirrors budget/views.py's `_flow_json`: floats for ECharts,
    kept out of services.py since it's chart presentation, not domain data."""
    rows = sorted(account_summaries, key=lambda row: row.net, reverse=True)
    return {
        "accounts": [row.account.name for row in rows],
        "net": [float(row.net) for row in rows],
    }


def _money_panel_context(settings: Settings) -> dict[str, Any]:
    """Context for the dashboard's money panel: hero stats, "money to move",
    the editable income list, and the per-account chart. Shared between the
    initial dashboard render and `update_income_amount`'s HTMX re-render so a
    salary edit and a fresh page load agree.

    # ponytail: fetches accounts twice (once inside budget_summary, once for
    # transfer_plan) instead of threading one list through both — the
    # dashboard isn't a hot path; thread it through if that changes.
    """
    period = active_period(settings.budget_mode, settings.budget_start_day)
    summary = budget_summary(settings.budget_mode, period)
    accounts = prefetched_accounts()
    return {
        "currency": settings.currency,
        "period": period,
        "summary": summary,
        "outgoings_pct": outgoings_percentage(summary.total_income, summary.total_outgoings),
        "transfer_groups": transfer_plan(accounts, settings.budget_mode, period),
        "income_streams": IncomeStream.objects.select_related("account").order_by("account__name", "name"),
        "account_chart_data": _account_chart_data(summary.accounts),
    }


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        settings = Settings.get()
        context.update(_money_panel_context(settings))
        period = context["period"]

        today = date.today()
        upcoming = month_events(today, today + timedelta(days=14), settings.budget_mode, settings.budget_start_day)
        upcoming_events = sorted(
            ((day, event) for day, events in upcoming.items() for event in events),
            key=lambda pair: pair[0],
        )[:6]

        pots = Pot.objects.select_related("linked_project").prefetch_related("entries")
        pot_rows = sorted(
            (pot_progress(pot, settings.budget_mode, period) for pot in pots),
            key=lambda row: (row.status != "behind", row.pot.target_date),
        )[:3]

        yearly_bills = upcoming_yearly_bills(prefetched_accounts(), today)[:5]

        context.update(
            {
                "upcoming_events": upcoming_events,
                "pot_rows": pot_rows,
                "yearly_bills": yearly_bills,
                "open_tasks": Task.objects.exclude(status=Task.Status.DONE)[:5],
                "recent_notes": Note.objects.all()[:5],
                "projects": Project.objects.prefetch_related("tasks", "pots")[:5],
            }
        )
        return context


@require_POST
def update_income_amount(request: HttpRequest, pk: int) -> HttpResponse:
    """Click-to-edit salary amount on the dashboard. Re-renders the whole
    money panel (hero stats + money-to-move + chart all move with a salary,
    since split/surplus transfers depend on it) rather than just the row.

    Unlike log_pot_entry, an invalid amount isn't silently dropped: the
    panel re-renders with the error attached so the row shows what's wrong.
    """
    income = get_object_or_404(IncomeStream, pk=pk)
    settings = Settings.get()
    form = IncomeAmountForm(request.POST, instance=income)
    error_income_id = None
    error_message = ""
    if form.is_valid():
        form.save()
    else:
        error_income_id = income.id
        error_message = " ".join(form.errors.get("amount", ["Invalid amount."]))

    context = _money_panel_context(settings)
    context["error_income_id"] = error_income_id
    context["error_message"] = error_message
    return render(request, "core/_money_panel.html", context)


class SettingsUpdateView(UpdateView):
    """Edits the singleton Settings row (currency, budget window, AI provider)."""

    form_class = SettingsForm
    template_name = "core/settings.html"
    success_url = reverse_lazy("core:settings")

    def get_object(self, queryset: Any = None) -> Settings:  # noqa: ARG002
        return Settings.get()

    def form_valid(self, form: Any) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, "Settings saved.")
        return response


@require_POST
def regenerate_webhook_secret(request: HttpRequest) -> HttpResponse:
    """Replace the inbound webhook HMAC secret with a freshly generated one."""
    settings = Settings.get()
    settings.webhook_inbound_secret = secrets.token_hex(32)
    settings.save(update_fields=["webhook_inbound_secret"])
    messages.success(request, "Webhook secret regenerated. Update any senders with the new value.")
    return redirect("core:settings")


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return (year, month) shifted by `delta` months (1-indexed month)."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


@dataclass
class CalendarDay:
    date: date
    in_month: bool
    is_today: bool
    events: list = field(default_factory=list)


class CalendarView(TemplateView):
    """Month grid aggregating task due dates, one-off due dates, pot target
    dates, recurring income/outgoing/transfer pay dates, and budget
    period-start markers.

    Recurring items are only plotted when they have `recurring_day` set (see
    FrequencyMixin); unscheduled ones fall back to the "Budget period" marker
    below as the stand-in.
    """

    template_name = "core/calendar.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        today = date.today()
        year = int(self.request.GET.get("year", today.year))
        month = int(self.request.GET.get("month", today.month))

        month_dates = calendar_module.Calendar(firstweekday=0).monthdatescalendar(year, month)
        range_start, range_end = month_dates[0][0], month_dates[-1][-1] + timedelta(days=1)
        settings = Settings.get()
        events = month_events(range_start, range_end, settings.budget_mode, settings.budget_start_day)

        # Recurring items with a scheduled `recurring_day` are plotted by
        # month_events() above; this marker covers the budget period boundary
        # itself (and stands in for any recurring item left unscheduled).
        overview_url = reverse("budget:overview")
        day = range_start
        while day < range_end:
            if active_period(settings.budget_mode, settings.budget_start_day, day).start == day:
                events[day].append(CalEvent("Budget period", overview_url, "bg-primary"))
            day += timedelta(days=1)

        weeks = [
            [
                CalendarDay(date=day, in_month=day.month == month, is_today=day == today, events=events[day])
                for day in week
            ]
            for week in month_dates
        ]

        prev_year, prev_month = _shift_month(year, month, -1)
        next_year, next_month = _shift_month(year, month, 1)

        context.update(
            {
                "weeks": weeks,
                "month_name": date(year, month, 1).strftime("%B %Y"),
                "prev_year": prev_year,
                "prev_month": prev_month,
                "next_year": next_year,
                "next_month": next_month,
            }
        )
        return context
