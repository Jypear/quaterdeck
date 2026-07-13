"""Unit tests for the budget engine (budget/services.py) and write views."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import RequestFactory, TestCase
from django.urls import reverse

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
    Period,
    account_summary,
    active_period,
    budget_summary,
    normalise,
    periods_between,
    pot_progress,
    to_display,
)
from budget.views import _requested_mode
from core.models import Settings


class NormaliseTests(TestCase):
    def test_all_frequency_mode_combinations(self) -> None:
        amount = Decimal("100")
        cases = {
            ("weekly", "weekly"): Decimal("100"),
            ("weekly", "monthly"): Decimal("100") * 52 / 12,
            ("weekly", "yearly"): Decimal("100") * 52,
            ("monthly", "weekly"): Decimal("100") * 12 / 52,
            ("monthly", "monthly"): Decimal("100"),
            ("monthly", "yearly"): Decimal("100") * 12,
            ("yearly", "weekly"): Decimal("100") / 52,
            ("yearly", "monthly"): Decimal("100") / 12,
            ("yearly", "yearly"): Decimal("100"),
        }
        for (frequency, mode), expected in cases.items():
            with self.subTest(frequency=frequency, mode=mode):
                assert normalise(amount, frequency, mode) == expected


class ActivePeriodTests(TestCase):
    def test_monthly_before_anchor_uses_previous_month(self) -> None:
        period = active_period(Settings.BudgetMode.MONTHLY, 28, today=date(2026, 7, 10))
        assert period == Period(date(2026, 6, 28), date(2026, 7, 28))

    def test_monthly_on_anchor_uses_current_month(self) -> None:
        period = active_period(Settings.BudgetMode.MONTHLY, 28, today=date(2026, 7, 28))
        assert period == Period(date(2026, 7, 28), date(2026, 8, 28))

    def test_monthly_clamps_start_day_to_short_month(self) -> None:
        period = active_period(Settings.BudgetMode.MONTHLY, 31, today=date(2026, 2, 15))
        assert period.start == date(2026, 1, 31)
        assert period.end == date(2026, 2, 28)

    def test_weekly_wraps_to_most_recent_anchor_weekday(self) -> None:
        # 2026-07-08 is a Wednesday (isoweekday 3); anchor is Monday (1).
        period = active_period(Settings.BudgetMode.WEEKLY, 1, today=date(2026, 7, 8))
        assert period == Period(date(2026, 7, 6), date(2026, 7, 13))

    def test_yearly_anchors_on_january(self) -> None:
        period = active_period(Settings.BudgetMode.YEARLY, 1, today=date(2026, 7, 8))
        assert period == Period(date(2026, 1, 1), date(2027, 1, 1))


class ModeOverrideWiringTests(TestCase):
    """Regression: the view must compute `active_period` from the requested
    `?mode=` override, not from the instance's stored `Settings.budget_mode` —
    otherwise switching the display mode re-normalises amounts but still
    filters one-offs/variances/pot-entries by the wrong window."""

    def test_mode_override_produces_a_different_period_than_stored_mode(self) -> None:
        request = RequestFactory().get("/", {"mode": "yearly"})
        settings = Settings(budget_mode=Settings.BudgetMode.MONTHLY, budget_start_day=1)

        requested_mode = _requested_mode(request, settings)
        assert requested_mode == "yearly"

        period = active_period(requested_mode, settings.budget_start_day, today=date(2026, 7, 8))
        assert period == Period(date(2026, 1, 1), date(2027, 1, 1))

        stored_mode_period = active_period(settings.budget_mode, settings.budget_start_day, today=date(2026, 7, 8))
        assert stored_mode_period != period


class PeriodsBetweenTests(TestCase):
    def test_monthly_counts_full_months(self) -> None:
        assert periods_between(date(2026, 1, 1), date(2026, 7, 1), "monthly") == 6

    def test_past_or_equal_end_returns_one(self) -> None:
        assert periods_between(date(2026, 7, 1), date(2026, 7, 1), "monthly") == 1
        assert periods_between(date(2026, 7, 1), date(2026, 1, 1), "monthly") == 1


class BudgetSummaryTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Personal")
        self.category = OutgoingCategory.objects.create(name="Bills")
        self.mode = Settings.BudgetMode.MONTHLY
        self.period = Period(date(2026, 7, 1), date(2026, 8, 1))

    def test_surplus_is_income_minus_outgoings(self) -> None:
        IncomeStream.objects.create(name="Salary", amount=Decimal("3000"), frequency="monthly", account=self.account)
        Outgoing.objects.create(
            name="Rent",
            amount=Decimal("1000"),
            category=self.category,
            frequency="monthly",
            account=self.account,
        )
        summary = budget_summary(self.mode, self.period)
        assert summary.total_income == Decimal("3000")
        assert summary.total_outgoings == Decimal("1000")
        assert summary.surplus == Decimal("2000")
        assert summary.adjusted_surplus == Decimal("2000")

    def test_overspend_variance_reduces_adjusted_surplus(self) -> None:
        outgoing = Outgoing.objects.create(
            name="Groceries",
            amount=Decimal("200"),
            category=self.category,
            frequency="monthly",
            account=self.account,
        )
        OutgoingVariance.objects.create(outgoing=outgoing, period_start=date(2026, 7, 1), actual_amount=Decimal("250"))
        summary = budget_summary(self.mode, self.period)
        assert summary.variance_total == Decimal("50")
        assert summary.adjusted_surplus == summary.surplus - Decimal("50")

    def test_one_off_only_counts_within_its_period(self) -> None:
        OneOffOutgoing.objects.create(
            name="Car service", amount=Decimal("300"), due_date=date(2026, 7, 15), account=self.account
        )
        OneOffOutgoing.objects.create(
            name="Next month's bill", amount=Decimal("500"), due_date=date(2026, 8, 15), account=self.account
        )
        summary = budget_summary(self.mode, self.period)
        assert summary.one_off_total == Decimal("300")

    def test_pot_contributions_reduce_unallocated_surplus(self) -> None:
        IncomeStream.objects.create(name="Salary", amount=Decimal("1000"), frequency="monthly", account=self.account)
        pot = Pot.objects.create(
            name="Holiday", target_amount=Decimal("2000"), target_date=date(2027, 1, 1), monthly_target=Decimal("100")
        )
        PotEntry.objects.create(pot=pot, period_start=date(2026, 7, 1), actual_amount=Decimal("100"))
        summary = budget_summary(self.mode, self.period)
        assert summary.pot_contributions == Decimal("100")
        assert summary.unallocated_surplus == summary.adjusted_surplus - Decimal("100")


class AccountSummaryTests(TestCase):
    def test_uncovered_when_outgoings_exceed_income(self) -> None:
        account = Account.objects.create(name="Joint")
        category = OutgoingCategory.objects.create(name="Bills")
        IncomeStream.objects.create(name="Salary", amount=Decimal("500"), frequency="monthly", account=account)
        Outgoing.objects.create(
            name="Rent", amount=Decimal("800"), category=category, frequency="monthly", account=account
        )
        period = Period(date(2026, 7, 1), date(2026, 8, 1))
        summary = account_summary(account, Settings.BudgetMode.MONTHLY, period)
        assert not summary.covered
        assert summary.net == Decimal("-300")


class PotProgressTests(TestCase):
    def test_behind_when_saved_less_than_expected(self) -> None:
        pot = Pot.objects.create(
            name="Holiday", target_amount=Decimal("1200"), target_date=date(2027, 1, 1), monthly_target=Decimal("100")
        )
        PotEntry.objects.create(pot=pot, period_start=date(2026, 5, 1), actual_amount=Decimal("50"))
        PotEntry.objects.create(pot=pot, period_start=date(2026, 6, 1), actual_amount=Decimal("50"))
        period = Period(date(2026, 6, 1), date(2026, 7, 1))
        progress = pot_progress(pot, Settings.BudgetMode.MONTHLY, period)
        assert progress.status == "behind"
        assert progress.saved_to_date == Decimal("100")
        assert progress.expected_to_date == Decimal("200")

    def test_ahead_when_saved_more_than_expected(self) -> None:
        pot = Pot.objects.create(
            name="Holiday", target_amount=Decimal("1200"), target_date=date(2027, 1, 1), monthly_target=Decimal("100")
        )
        PotEntry.objects.create(pot=pot, period_start=date(2026, 6, 1), actual_amount=Decimal("150"))
        period = Period(date(2026, 6, 1), date(2026, 7, 1))
        progress = pot_progress(pot, Settings.BudgetMode.MONTHLY, period)
        assert progress.status == "ahead"

    def test_per_period_needed_when_target_already_met(self) -> None:
        pot = Pot.objects.create(
            name="Holiday", target_amount=Decimal("100"), target_date=date(2026, 8, 1), monthly_target=Decimal("100")
        )
        PotEntry.objects.create(pot=pot, period_start=date(2026, 7, 1), actual_amount=Decimal("100"))
        period = Period(date(2026, 7, 1), date(2026, 8, 1))
        progress = pot_progress(pot, Settings.BudgetMode.MONTHLY, period)
        assert progress.per_period_needed == Decimal("0")


class LogVarianceViewTests(TestCase):
    """POSTing to log_variance is the only way to fill OutgoingVariance from the browser."""

    def setUp(self) -> None:
        self.account = Account.objects.create(name="Personal")
        self.category = OutgoingCategory.objects.create(name="Bills")
        self.outgoing = Outgoing.objects.create(
            name="Rent", amount=Decimal("1000"), category=self.category, frequency="monthly", account=self.account
        )
        settings = Settings.get()
        self.period = active_period(settings.budget_mode, settings.budget_start_day)

    def test_post_creates_variance_for_the_active_period(self) -> None:
        url = reverse("budget:log_variance", args=[self.outgoing.id])
        response = self.client.post(url, {"actual_amount": "1200"})
        assert response.status_code == 200
        variance = OutgoingVariance.objects.get(outgoing=self.outgoing, period_start=self.period.start)
        assert variance.actual_amount == Decimal("1200")

    def test_second_post_same_period_overwrites_instead_of_duplicating(self) -> None:
        url = reverse("budget:log_variance", args=[self.outgoing.id])
        self.client.post(url, {"actual_amount": "1200"})
        self.client.post(url, {"actual_amount": "1300"})
        assert OutgoingVariance.objects.filter(outgoing=self.outgoing).count() == 1
        assert OutgoingVariance.objects.get(outgoing=self.outgoing).actual_amount == Decimal("1300")

    def test_logged_variance_flows_into_adjusted_surplus(self) -> None:
        url = reverse("budget:log_variance", args=[self.outgoing.id])
        self.client.post(url, {"actual_amount": "1200"})
        summary = budget_summary(Settings.BudgetMode.MONTHLY, self.period)
        assert summary.variance_total == Decimal("200")


class LogPotEntryViewTests(TestCase):
    """POSTing to log_pot_entry is the only way to fill PotEntry from the browser."""

    def setUp(self) -> None:
        self.pot = Pot.objects.create(
            name="Holiday",
            target_amount=Decimal("2000"),
            target_date=date(2030, 1, 1),
            monthly_target=Decimal("100"),
        )
        settings = Settings.get()
        self.period = active_period(settings.budget_mode, settings.budget_start_day)

    def test_post_creates_pot_entry_for_the_active_period(self) -> None:
        url = reverse("budget:log_pot_entry", args=[self.pot.id])
        response = self.client.post(url, {"actual_amount": "150"})
        assert response.status_code == 200
        entry = PotEntry.objects.get(pot=self.pot, period_start=self.period.start)
        assert entry.actual_amount == Decimal("150")

    def test_logged_entry_flows_into_pot_progress(self) -> None:
        url = reverse("budget:log_pot_entry", args=[self.pot.id])
        self.client.post(url, {"actual_amount": "150"})
        progress = pot_progress(self.pot, Settings.BudgetMode.MONTHLY, self.period)
        assert progress.saved_to_date == Decimal("150")


class OneOffPotCoverageTests(TestCase):
    """Pot-linked one-offs get a computed `.pot_covered` / `.pot_saved` via _accounts_context."""

    def setUp(self) -> None:
        self.account = Account.objects.create(name="Personal")
        self.pot = Pot.objects.create(
            name="Car fund", target_amount=Decimal("1000"), target_date=date(2027, 1, 1), monthly_target=Decimal("50")
        )

    def _oneoff(self) -> OneOffOutgoing:
        response = self.client.get(reverse("budget:accounts"))
        assert response.status_code == 200
        summary = next(s for s in response.context["account_summaries"] if s.account.id == self.account.id)
        return next(iter(summary.account.one_off_outgoings.all()))

    def test_covered_when_pot_balance_meets_amount(self) -> None:
        PotEntry.objects.create(pot=self.pot, period_start=date(2026, 7, 1), actual_amount=Decimal("300"))
        OneOffOutgoing.objects.create(
            name="Service", amount=Decimal("250"), due_date=date(2026, 9, 1), account=self.account, linked_pot=self.pot
        )
        oneoff = self._oneoff()
        assert oneoff.pot_saved == Decimal("300")
        assert oneoff.pot_covered is True

    def test_uncovered_when_pot_balance_below_amount(self) -> None:
        PotEntry.objects.create(pot=self.pot, period_start=date(2026, 7, 1), actual_amount=Decimal("100"))
        OneOffOutgoing.objects.create(
            name="Service", amount=Decimal("250"), due_date=date(2026, 9, 1), account=self.account, linked_pot=self.pot
        )
        oneoff = self._oneoff()
        assert oneoff.pot_saved == Decimal("100")
        assert oneoff.pot_covered is False

    def test_unlinked_oneoff_has_no_coverage_attributes(self) -> None:
        OneOffOutgoing.objects.create(
            name="Service", amount=Decimal("250"), due_date=date(2026, 9, 1), account=self.account
        )
        oneoff = self._oneoff()
        assert not hasattr(oneoff, "pot_covered")


class AcceptPotContributionViewTests(TestCase):
    def setUp(self) -> None:
        self.pot = Pot.objects.create(
            name="Holiday", target_amount=Decimal("1200"), target_date=date(2027, 1, 1), monthly_target=Decimal("100")
        )
        PotEntry.objects.create(pot=self.pot, period_start=date(2026, 6, 1), actual_amount=Decimal("50"))
        settings = Settings.get()
        self.period = active_period(settings.budget_mode, settings.budget_start_day)

    def test_accept_sets_monthly_target_to_suggested_value(self) -> None:
        expected = to_display(pot_progress(self.pot, Settings.BudgetMode.MONTHLY, self.period).per_period_needed)
        url = reverse("budget:accept_pot_contribution", args=[self.pot.id])
        response = self.client.post(url)
        assert response.status_code == 200
        self.pot.refresh_from_db()
        assert self.pot.monthly_target == expected


class OutgoingCreateViewTests(TestCase):
    """Smoke test for the CRUD views — confirms the CBV + form wiring works end to end."""

    def test_post_creates_outgoing_and_redirects_to_accounts(self) -> None:
        account = Account.objects.create(name="Personal")
        category = OutgoingCategory.objects.create(name="Bills")
        url = reverse("budget:outgoing_add")
        response = self.client.post(
            url,
            {
                "name": "Internet",
                "amount": "50",
                "frequency": "monthly",
                "category": category.id,
                "account": account.id,
            },
        )
        assert response.status_code == 302
        assert Outgoing.objects.filter(name="Internet", account=account).exists()


class NewCrudSmokeTests(TestCase):
    """Smoke tests for the previously admin-only models' new HTML CRUD."""

    def test_category_create(self) -> None:
        response = self.client.post(reverse("budget:category_add"), {"name": "Subscriptions"})
        assert response.status_code == 302
        assert OutgoingCategory.objects.filter(name="Subscriptions").exists()

    def test_transfer_create(self) -> None:
        personal = Account.objects.create(name="Personal")
        joint = Account.objects.create(name="Joint")
        response = self.client.post(
            reverse("budget:transfer_add"),
            {
                "name": "Joint contribution",
                "amount": "200",
                "frequency": "monthly",
                "from_account": personal.id,
                "to_account": joint.id,
            },
        )
        assert response.status_code == 302
        assert Transfer.objects.filter(name="Joint contribution", from_account=personal, to_account=joint).exists()

    def test_oneoff_create(self) -> None:
        account = Account.objects.create(name="Personal")
        response = self.client.post(
            reverse("budget:oneoff_add"),
            {"name": "Car service", "amount": "300", "due_date": "2026-11-01", "account": account.id},
        )
        assert response.status_code == 302
        assert OneOffOutgoing.objects.filter(name="Car service", account=account).exists()

    def test_pot_create(self) -> None:
        response = self.client.post(
            reverse("budget:pot_add"),
            {
                "name": "Holiday 2026",
                "target_amount": "2000",
                "target_date": "2026-12-01",
                "monthly_target": "100",
            },
        )
        assert response.status_code == 302
        assert Pot.objects.filter(name="Holiday 2026").exists()
