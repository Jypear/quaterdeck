"""Core views — dashboard, calendar, and settings."""

from __future__ import annotations

import calendar as calendar_module
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView, UpdateView

from budget.services import active_period
from core.events import CalEvent, month_events
from core.forms import SettingsForm
from core.models import Settings

if TYPE_CHECKING:
    from django.http import HttpResponse


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"


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
    dates, and budget period-start markers.

    Recurring income/outgoings/transfers have no per-entry date field (only a
    `frequency`), so they can't be placed on a specific day — deferred; see
    the "Budget period" marker below as the stand-in.
    """

    template_name = "core/calendar.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        today = date.today()
        year = int(self.request.GET.get("year", today.year))
        month = int(self.request.GET.get("month", today.month))

        month_dates = calendar_module.Calendar(firstweekday=0).monthdatescalendar(year, month)
        range_start, range_end = month_dates[0][0], month_dates[-1][-1] + timedelta(days=1)
        events = month_events(range_start, range_end)

        settings = Settings.get()
        # ponytail: budget period markers only — no per-entry date on recurring
        # income/outgoings/transfers to plot individually. Add if a per-entry
        # date field is ever introduced.
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
