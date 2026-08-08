"""Tests for core/events.py (calendar event bucketing) and the calendar view."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from budget.models import Account, IncomeStream, OneOffOutgoing, Outgoing, OutgoingCategory, Pot, Transfer
from core.events import month_events
from core.models import Settings
from tasks.models import Task


class MonthEventsDynamicTransferTests(TestCase):
    """Regression: split/surplus transfers used to show as `£None` on the
    calendar/dashboard since their `amount` field is null — the label must
    use the resolved amount instead."""

    def test_split_transfer_shows_resolved_amount(self) -> None:
        source = Account.objects.create(name="Personal")
        destination = Account.objects.create(name="Joint")
        category = OutgoingCategory.objects.create(name="Bills")
        IncomeStream.objects.create(name="Salary", amount=Decimal("3000"), frequency="monthly", account=source)
        Outgoing.objects.create(
            name="Rent", amount=Decimal("1000"), category=category, frequency="monthly", account=destination
        )
        Transfer.objects.create(
            name="Contribution",
            from_account=source,
            to_account=destination,
            calc_method=Transfer.CalcMethod.SPLIT,
            frequency="monthly",
            recurring_day=15,
        )
        events = month_events(date(2026, 7, 1), date(2026, 8, 1), Settings.BudgetMode.MONTHLY, 1)
        label = events[date(2026, 7, 15)][0].label
        assert "None" not in label
        assert label == "Contribution £1000.00"


class MetricsViewTests(TestCase):
    def test_metrics_are_exposed_without_a_token(self) -> None:
        response = self.client.get(reverse("metrics"))
        assert response.status_code == 200
        assert b"django_http_requests" in response.content

    def test_metrics_require_bearer_token_when_configured(self) -> None:
        with patch.dict(os.environ, {"METRICS_TOKEN": "secret"}):
            unauthenticated = self.client.get(reverse("metrics"))
            assert unauthenticated.status_code == 401

            authenticated = self.client.get(reverse("metrics"), HTTP_AUTHORIZATION="Bearer secret")
            assert authenticated.status_code == 200


class MonthEventsTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Personal")

    def test_task_due_date_is_bucketed(self) -> None:
        task = Task.objects.create(title="Renew passport", due_date=date(2026, 7, 15))
        events = month_events(date(2026, 7, 1), date(2026, 8, 1), Settings.BudgetMode.MONTHLY, 1)
        assert events[date(2026, 7, 15)][0].label == "Renew passport"
        assert reverse("tasks:task_edit", args=[task.id]) in events[date(2026, 7, 15)][0].url

    def test_one_off_due_date_is_bucketed(self) -> None:
        OneOffOutgoing.objects.create(
            name="Car service", amount=Decimal("300"), due_date=date(2026, 7, 20), account=self.account
        )
        events = month_events(date(2026, 7, 1), date(2026, 8, 1), Settings.BudgetMode.MONTHLY, 1)
        assert "Car service" in events[date(2026, 7, 20)][0].label

    def test_pot_target_date_is_bucketed(self) -> None:
        Pot.objects.create(
            name="Holiday", target_amount=Decimal("1000"), target_date=date(2026, 7, 31), monthly_target=Decimal("50")
        )
        events = month_events(date(2026, 7, 1), date(2026, 8, 1), Settings.BudgetMode.MONTHLY, 1)
        assert "Holiday" in events[date(2026, 7, 31)][0].label

    def test_dates_outside_range_are_excluded(self) -> None:
        Task.objects.create(title="Next month", due_date=date(2026, 8, 1))
        events = month_events(date(2026, 7, 1), date(2026, 8, 1), Settings.BudgetMode.MONTHLY, 1)
        assert date(2026, 8, 1) not in events


class SettingsViewTests(TestCase):
    def test_save_with_blank_key_field_keeps_existing_key(self) -> None:
        settings = Settings.get()
        settings.ai_provider = Settings.AiProvider.ANTHROPIC
        settings.ai_api_key = "sk-secret"
        settings.ai_model = "claude-sonnet-5"
        settings.save()

        self.client.post(
            reverse("core:settings"),
            {
                "currency": "GBP",
                "budget_mode": Settings.BudgetMode.MONTHLY,
                "budget_start_day": 1,
                "ai_provider": Settings.AiProvider.ANTHROPIC,
                "ai_api_key": "",  # left blank — should not wipe the stored key
                "ai_model": "claude-sonnet-5",
            },
        )

        settings.refresh_from_db()
        assert settings.ai_api_key == "sk-secret"

    def test_save_with_new_key_replaces_existing_key(self) -> None:
        settings = Settings.get()
        settings.ai_api_key = "sk-old"
        settings.save()

        self.client.post(
            reverse("core:settings"),
            {
                "currency": "GBP",
                "budget_mode": Settings.BudgetMode.MONTHLY,
                "budget_start_day": 1,
                "ai_provider": Settings.AiProvider.NONE,
                "ai_api_key": "sk-new",
                "ai_model": "",
            },
        )

        settings.refresh_from_db()
        assert settings.ai_api_key == "sk-new"


class DashboardViewTests(TestCase):
    """No test previously touched core:dashboard at all."""

    def test_dashboard_renders_the_money_panel(self) -> None:
        account = Account.objects.create(name="Personal")
        IncomeStream.objects.create(name="Salary", amount=Decimal("3000"), frequency="monthly", account=account)

        response = self.client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        assert "transfer_groups" in response.context
        assert "income_streams" in response.context
        assert response.context["income_streams"][0].name == "Salary"


class IncomeAmountUpdateTests(TestCase):
    """update_income_amount is the dashboard's click-to-edit salary field —
    it has to actually move dependent split transfers, and unlike
    log_pot_entry it must not silently drop an invalid amount."""

    def setUp(self) -> None:
        self.a = Account.objects.create(name="A Personal")
        self.b = Account.objects.create(name="B Personal")
        self.joint = Account.objects.create(name="Joint", account_type="joint")
        category = OutgoingCategory.objects.create(name="Bills")
        self.a_salary = IncomeStream.objects.create(
            name="A Salary", amount=Decimal("3000"), frequency="monthly", account=self.a
        )
        IncomeStream.objects.create(name="B Salary", amount=Decimal("2000"), frequency="monthly", account=self.b)
        Outgoing.objects.create(
            name="Joint bills", amount=Decimal("1500"), category=category, frequency="monthly", account=self.joint
        )
        self.a_to_joint = Transfer.objects.create(
            name="A to joint", from_account=self.a, to_account=self.joint, calc_method=Transfer.CalcMethod.SPLIT
        )

    def test_valid_amount_updates_and_moves_dependent_transfers(self) -> None:
        settings = Settings.get()
        settings.budget_start_day = 1
        settings.save()

        response = self.client.post(reverse("core:income_amount", args=[self.a_salary.id]), {"amount": "4000"})

        assert response.status_code == 200
        self.a_salary.refresh_from_db()
        assert self.a_salary.amount == Decimal("4000")

        groups = response.context["transfer_groups"]
        row = next(r for g in groups for r in g.rows if r.transfer.id == self.a_to_joint.id)
        assert row.amount != Decimal("500")  # the pre-raise split share

    def test_invalid_amount_is_rejected_not_silently_dropped(self) -> None:
        response = self.client.post(reverse("core:income_amount", args=[self.a_salary.id]), {"amount": "not-a-number"})

        assert response.status_code == 200
        self.a_salary.refresh_from_db()
        assert self.a_salary.amount == Decimal("3000")
        assert response.context["error_income_id"] == self.a_salary.id
        assert response.context["error_message"]


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
