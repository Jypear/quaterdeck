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
    account_timelines,
    active_period,
    budget_flow,
    budget_summary,
    normalise,
    periods_between,
    pot_progress,
    resolve_transfer_amounts,
    scheduled_dates,
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


class ScheduledDatesTests(TestCase):
    """`recurring_day` + `weekend_adjust` + weekly interval/anchor scheduling."""

    def setUp(self) -> None:
        self.account = Account.objects.create(name="Personal")
        self.category = OutgoingCategory.objects.create(name="Bills")

    def test_monthly_weekend_adjust_before_after_and_blank(self) -> None:
        # 2026-09-05 is a Saturday.
        window = (date(2026, 9, 1), date(2026, 10, 1))

        before = Outgoing.objects.create(
            name="Mortgage",
            amount=Decimal("1000"),
            category=self.category,
            account=self.account,
            frequency="monthly",
            recurring_day=5,
            weekend_adjust="before",
        )
        assert scheduled_dates(before, *window) == [date(2026, 9, 4)]

        after = Outgoing.objects.create(
            name="Mortgage",
            amount=Decimal("1000"),
            category=self.category,
            account=self.account,
            frequency="monthly",
            recurring_day=5,
            weekend_adjust="after",
        )
        assert scheduled_dates(after, *window) == [date(2026, 9, 7)]

        unadjusted = Outgoing.objects.create(
            name="Mortgage",
            amount=Decimal("1000"),
            category=self.category,
            account=self.account,
            frequency="monthly",
            recurring_day=5,
        )
        assert scheduled_dates(unadjusted, *window) == [date(2026, 9, 5)]

    def test_salary_moves_to_friday_before_weekend(self) -> None:
        # 2026-02-28 is a Saturday.
        salary = IncomeStream.objects.create(
            name="Salary",
            amount=Decimal("3000"),
            account=self.account,
            frequency="monthly",
            recurring_day=28,
            weekend_adjust="before",
        )
        dates = scheduled_dates(salary, date(2026, 2, 1), date(2026, 3, 1))
        assert dates == [date(2026, 2, 27)]

    def test_recurring_day_clamps_to_short_month(self) -> None:
        salary = IncomeStream.objects.create(
            name="Salary", amount=Decimal("3000"), account=self.account, frequency="monthly", recurring_day=31
        )
        # Feb 2026 has 28 days, so day 31 clamps to the 28th.
        dates = scheduled_dates(salary, date(2026, 2, 1), date(2026, 3, 1))
        assert dates == [date(2026, 2, 28)]

    def test_fortnightly_weekly_interval_only_matches_alternating_weeks(self) -> None:
        # 2026-07-06/13/20/27 are all Mondays; anchor on the 6th with interval=2
        # should only match the 6th and 20th within July.
        wages = IncomeStream.objects.create(
            name="Wages",
            amount=Decimal("500"),
            account=self.account,
            frequency="weekly",
            recurring_day=1,
            week_interval=2,
            week_anchor=date(2026, 7, 6),
        )
        dates = scheduled_dates(wages, date(2026, 7, 1), date(2026, 8, 1))
        assert dates == [date(2026, 7, 6), date(2026, 7, 20)]


class AccountTimelinesTests(TestCase):
    """`account_timelines` builds each account's ordered, running-balance stops."""

    def setUp(self) -> None:
        self.personal = Account.objects.create(name="Personal")
        self.joint = Account.objects.create(name="Joint")
        self.category = OutgoingCategory.objects.create(name="Bills")

    def test_stops_are_ordered_signed_and_running_balance_starts_at_zero(self) -> None:
        IncomeStream.objects.create(
            name="Salary",
            amount=Decimal("1000"),
            account=self.personal,
            frequency="monthly",
            recurring_day=1,
        )
        Outgoing.objects.create(
            name="Rent",
            amount=Decimal("400"),
            category=self.category,
            account=self.personal,
            frequency="monthly",
            recurring_day=15,
        )

        lanes = account_timelines(date(2026, 7, 1), date(2026, 8, 1))
        lane = next(lane for lane in lanes if lane.account.id == self.personal.id)

        assert [stop.date for stop in lane.stops] == [date(2026, 7, 1), date(2026, 7, 15)]
        assert lane.stops[0].amount == Decimal("1000")
        assert lane.stops[0].kind == "income"
        assert lane.stops[0].balance == Decimal("1000")
        assert lane.stops[1].amount == Decimal("-400")
        assert lane.stops[1].balance == Decimal("600")
        assert lane.end_balance == Decimal("600")

    def test_transfer_appears_on_both_lanes_sharing_a_transfer_id(self) -> None:
        transfer = Transfer.objects.create(
            name="Joint contribution",
            from_account=self.personal,
            to_account=self.joint,
            amount=Decimal("200"),
            frequency="monthly",
            recurring_day=10,
        )

        lanes = {lane.account.id: lane for lane in account_timelines(date(2026, 7, 1), date(2026, 8, 1))}

        out_stop = lanes[self.personal.id].stops[0]
        in_stop = lanes[self.joint.id].stops[0]
        assert out_stop.amount == Decimal("-200")
        assert in_stop.amount == Decimal("200")
        assert out_stop.transfer_id == in_stop.transfer_id == transfer.id

    def test_one_off_outside_window_is_excluded(self) -> None:
        OneOffOutgoing.objects.create(
            name="Car service", amount=Decimal("300"), due_date=date(2026, 9, 1), account=self.personal
        )
        lanes = account_timelines(date(2026, 7, 1), date(2026, 8, 1))
        lane = next(lane for lane in lanes if lane.account.id == self.personal.id)
        assert lane.stops == []


class BudgetFlowTests(TestCase):
    """`budget_flow` builds the Sankey-shaped graph for the Flow view."""

    def setUp(self) -> None:
        self.personal = Account.objects.create(name="Personal")
        self.joint = Account.objects.create(name="Joint")
        self.category = OutgoingCategory.objects.create(name="Bills")
        self.mode = Settings.BudgetMode.MONTHLY
        self.period = Period(date(2026, 7, 1), date(2026, 8, 1))

    def test_income_balances_against_bills_and_banked_surplus(self) -> None:
        """Transfers move money between account nodes without leaving the
        account layer, so conservation excludes them: income in == bills +
        surplus out."""
        IncomeStream.objects.create(name="Salary", amount=Decimal("2000"), frequency="monthly", account=self.personal)
        Outgoing.objects.create(
            name="Rent", amount=Decimal("800"), category=self.category, frequency="monthly", account=self.personal
        )
        Transfer.objects.create(
            name="Joint contribution",
            from_account=self.personal,
            to_account=self.joint,
            amount=Decimal("300"),
            frequency="monthly",
        )
        graph = budget_flow(self.mode, self.period)

        total_income = sum((link.value for link in graph.links if link.kind == "income"), Decimal("0"))
        total_spent_or_banked = sum(
            (link.value for link in graph.links if link.kind in ("bill", "surplus")), Decimal("0")
        )
        assert total_income == Decimal("2000")
        assert total_income == total_spent_or_banked

    def test_transfers_between_same_pair_are_netted_into_one_link(self) -> None:
        Transfer.objects.create(
            name="To joint",
            from_account=self.personal,
            to_account=self.joint,
            amount=Decimal("500"),
            frequency="monthly",
        )
        Transfer.objects.create(
            name="Back to personal",
            from_account=self.joint,
            to_account=self.personal,
            amount=Decimal("200"),
            frequency="monthly",
        )
        graph = budget_flow(self.mode, self.period)
        transfer_links = [link for link in graph.links if link.kind == "transfer"]
        assert len(transfer_links) == 1
        assert transfer_links[0].source == "Personal"
        assert transfer_links[0].target == "Joint"
        assert transfer_links[0].value == Decimal("300")

    def test_pot_contribution_and_unallocated_split_the_surplus(self) -> None:
        IncomeStream.objects.create(name="Salary", amount=Decimal("1000"), frequency="monthly", account=self.personal)
        pot = Pot.objects.create(
            name="Holiday", target_amount=Decimal("2000"), target_date=date(2027, 1, 1), monthly_target=Decimal("100")
        )
        PotEntry.objects.create(pot=pot, period_start=date(2026, 7, 1), actual_amount=Decimal("300"))
        graph = budget_flow(self.mode, self.period)

        pot_link = next(link for link in graph.links if link.kind == "pot")
        unallocated_link = next(link for link in graph.links if link.kind == "unallocated")
        assert pot_link.value == Decimal("300")
        assert unallocated_link.value == Decimal("700")

    def test_duplicate_bill_names_get_disambiguated(self) -> None:
        Outgoing.objects.create(
            name="Insurance", amount=Decimal("50"), category=self.category, frequency="monthly", account=self.personal
        )
        Outgoing.objects.create(
            name="Insurance", amount=Decimal("30"), category=self.category, frequency="monthly", account=self.joint
        )
        graph = budget_flow(self.mode, self.period)
        names = sorted(node.name for node in graph.nodes if node.kind == "bill")
        assert names == ["Insurance", "Insurance (2)"]

    def test_overspent_account_contributes_no_surplus_link(self) -> None:
        IncomeStream.objects.create(name="Salary", amount=Decimal("500"), frequency="monthly", account=self.personal)
        Outgoing.objects.create(
            name="Rent", amount=Decimal("800"), category=self.category, frequency="monthly", account=self.personal
        )
        graph = budget_flow(self.mode, self.period)
        assert not any(link.kind == "surplus" for link in graph.links)
        assert not any(node.kind == "surplus" for node in graph.nodes)


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


class DynamicTransferTests(TestCase):
    """The household flow this feature was built for: two salaries split the
    joint account's funding need by how much each earns, then sweep whatever
    personal money is left into a shared spends account."""

    def setUp(self) -> None:
        self.mode = Settings.BudgetMode.MONTHLY
        self.period = Period(date(2026, 7, 1), date(2026, 8, 1))
        self.category = OutgoingCategory.objects.create(name="Bills")
        self.a = Account.objects.create(name="A Personal")
        self.b = Account.objects.create(name="B Personal")
        self.joint = Account.objects.create(name="Joint", account_type="joint")
        self.savings = Account.objects.create(name="Savings", account_type="savings")
        self.spends = Account.objects.create(name="Spends")
        IncomeStream.objects.create(name="A Salary", amount=Decimal("3000"), frequency="monthly", account=self.a)
        IncomeStream.objects.create(name="B Salary", amount=Decimal("2000"), frequency="monthly", account=self.b)
        Outgoing.objects.create(
            name="Joint bills", amount=Decimal("1500"), category=self.category, frequency="monthly", account=self.joint
        )
        Transfer.objects.create(
            name="Joint to savings",
            from_account=self.joint,
            to_account=self.savings,
            amount=Decimal("500"),
            frequency="monthly",
            calc_method=Transfer.CalcMethod.FIXED,
        )

    def _resolve(self) -> dict[int, Decimal]:
        accounts = list(
            Account.objects.prefetch_related(
                "income_streams", "outgoings", "transfers_in", "transfers_out", "one_off_outgoings"
            )
        )
        return resolve_transfer_amounts(accounts, self.mode, self.period)

    def test_split_shares_by_salary_difference(self) -> None:
        a_to_joint = Transfer.objects.create(
            name="A to joint", from_account=self.a, to_account=self.joint, calc_method=Transfer.CalcMethod.SPLIT
        )
        b_to_joint = Transfer.objects.create(
            name="B to joint", from_account=self.b, to_account=self.joint, calc_method=Transfer.CalcMethod.SPLIT
        )
        amounts = self._resolve()
        # required = 1500 bills + 500 to savings - 0 income = 2000; mean salary = 2500
        assert amounts[a_to_joint.id] == Decimal("1500")  # 1000 + (3000 - 2500)
        assert amounts[b_to_joint.id] == Decimal("500")  # 1000 - (3000 - 2500)... i.e. 1000 - 500

    def test_surplus_sweeps_the_remainder_after_the_split_contribution(self) -> None:
        a_to_joint = Transfer.objects.create(
            name="A to joint", from_account=self.a, to_account=self.joint, calc_method=Transfer.CalcMethod.SPLIT
        )
        b_to_joint = Transfer.objects.create(
            name="B to joint", from_account=self.b, to_account=self.joint, calc_method=Transfer.CalcMethod.SPLIT
        )
        a_to_spends = Transfer.objects.create(
            name="A to spends", from_account=self.a, to_account=self.spends, calc_method=Transfer.CalcMethod.SURPLUS
        )
        b_to_spends = Transfer.objects.create(
            name="B to spends", from_account=self.b, to_account=self.spends, calc_method=Transfer.CalcMethod.SURPLUS
        )
        amounts = self._resolve()
        assert amounts[a_to_spends.id] == Decimal("3000") - amounts[a_to_joint.id]
        assert amounts[b_to_spends.id] == Decimal("2000") - amounts[b_to_joint.id]

        summary = budget_summary(self.mode, self.period)
        joint_summary = next(s for s in summary.accounts if s.account.id == self.joint.id)
        assert joint_summary.net == Decimal("0")

    def test_negative_share_clamps_to_zero(self) -> None:
        # Joint's own income already covers bills + the savings transfer, so
        # the funding need (and each split share) should clamp at zero.
        IncomeStream.objects.create(
            name="Joint income", amount=Decimal("5000"), frequency="monthly", account=self.joint
        )
        a_to_joint = Transfer.objects.create(
            name="A to joint", from_account=self.a, to_account=self.joint, calc_method=Transfer.CalcMethod.SPLIT
        )
        b_to_joint = Transfer.objects.create(
            name="B to joint", from_account=self.b, to_account=self.joint, calc_method=Transfer.CalcMethod.SPLIT
        )
        amounts = self._resolve()
        # Without clamping, B's share would be 0 - (3000-2500) = -500.
        assert amounts[b_to_joint.id] == Decimal("0")
        assert amounts[a_to_joint.id] == Decimal("500")


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
                "calc_method": "fixed",
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


class DatePrefillTests(TestCase):
    """Regression: the calendar's "+" links pass `?date=` to pre-fill due_date/target_date."""

    def test_oneoff_valid_date_prefills_due_date(self) -> None:
        response = self.client.get(reverse("budget:oneoff_add"), {"date": "2026-07-15"})
        assert response.context["form"].initial["due_date"] == date(2026, 7, 15)
        # The rendered <input type="date"> needs an ISO value or the browser
        # silently blanks it, regardless of locale (en-gb formats DD/MM/YYYY).
        assert 'value="2026-07-15"' in response.content.decode()

    def test_pot_valid_date_prefills_target_date(self) -> None:
        response = self.client.get(reverse("budget:pot_add"), {"date": "2026-07-15"})
        assert response.context["form"].initial["target_date"] == date(2026, 7, 15)
        assert 'value="2026-07-15"' in response.content.decode()

    def test_missing_or_invalid_date_leaves_it_unset(self) -> None:
        response = self.client.get(reverse("budget:oneoff_add"))
        assert "due_date" not in response.context["form"].initial

        response = self.client.get(reverse("budget:oneoff_add"), {"date": "nope"})
        assert "due_date" not in response.context["form"].initial
