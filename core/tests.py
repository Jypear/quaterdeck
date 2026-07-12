"""Tests for core/events.py (calendar event bucketing) and the calendar view."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from budget.models import Account, OneOffOutgoing, Pot
from core.events import month_events
from core.models import Settings
from tasks.models import Task


class MonthEventsTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Personal")

    def test_task_due_date_is_bucketed(self) -> None:
        task = Task.objects.create(title="Renew passport", due_date=date(2026, 7, 15))
        events = month_events(date(2026, 7, 1), date(2026, 8, 1))
        assert events[date(2026, 7, 15)][0].label == "Renew passport"
        assert reverse("tasks:task_edit", args=[task.id]) in events[date(2026, 7, 15)][0].url

    def test_one_off_due_date_is_bucketed(self) -> None:
        OneOffOutgoing.objects.create(
            name="Car service", amount=Decimal("300"), due_date=date(2026, 7, 20), account=self.account
        )
        events = month_events(date(2026, 7, 1), date(2026, 8, 1))
        assert "Car service" in events[date(2026, 7, 20)][0].label

    def test_pot_target_date_is_bucketed(self) -> None:
        Pot.objects.create(
            name="Holiday", target_amount=Decimal("1000"), target_date=date(2026, 7, 31), monthly_target=Decimal("50")
        )
        events = month_events(date(2026, 7, 1), date(2026, 8, 1))
        assert "Holiday" in events[date(2026, 7, 31)][0].label

    def test_dates_outside_range_are_excluded(self) -> None:
        Task.objects.create(title="Next month", due_date=date(2026, 8, 1))
        events = month_events(date(2026, 7, 1), date(2026, 8, 1))
        assert date(2026, 8, 1) not in events


class CalendarViewTests(TestCase):
    def test_budget_period_start_gets_a_marker(self) -> None:
        settings = Settings.get()
        settings.budget_mode = Settings.BudgetMode.MONTHLY
        settings.budget_start_day = 1
        settings.save()

        response = self.client.get(reverse("core:calendar"), {"year": 2026, "month": 7})
        assert response.status_code == 200

        first_of_month = next(day for week in response.context["weeks"] for day in week if day.date == date(2026, 7, 1))
        assert any(event.label == "Budget period" for event in first_of_month.events)

    def test_page_renders_for_a_month_with_no_events(self) -> None:
        response = self.client.get(reverse("core:calendar"), {"year": 2026, "month": 7})
        assert response.status_code == 200
