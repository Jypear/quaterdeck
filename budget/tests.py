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
    Pot,
    PotEntry,
    Transfer,
)
from budget.services import (
    AccountLane,
    Period,
    TimelineStop,
    account_summary,
    account_timelines,
    active_period,
    budget_flow,
    budget_summary,
    category_totals,
    normalise,
    outgoing_amount,
    outgoing_rows,
    periods_between,
    pot_progress,
    prefetched_accounts,
    resolve_transfer_amounts,
    scheduled_dates,
    sort_outgoing_rows,
    to_display,
    transfer_plan,
    upcoming_yearly_bills,
)
from budget.views import _assign_label_dys, _requested_mode, _timeline_svg
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
    filters one-offs/pot-entries by the wrong window."""

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

    def test_group_by_category_collapses_same_account_bills_into_one_node(self) -> None:
        Outgoing.objects.create(
            name="Netflix", amount=Decimal("15"), category=self.category, frequency="monthly", account=self.personal
        )
        Outgoing.objects.create(
            name="Spotify", amount=Decimal("10"), category=self.category, frequency="monthly", account=self.personal
        )
        graph = budget_flow(self.mode, self.period, group_by_category=True)
        bill_links = [link for link in graph.links if link.kind == "bill"]
        assert len(bill_links) == 1
        assert bill_links[0].target == "Bills"
        assert bill_links[0].value == Decimal("25")

    def test_group_by_category_shares_one_node_across_accounts(self) -> None:
        Outgoing.objects.create(
            name="Home insurance",
            amount=Decimal("20"),
            category=self.category,
            frequency="monthly",
            account=self.personal,
        )
        Outgoing.objects.create(
            name="Car insurance", amount=Decimal("30"), category=self.category, frequency="monthly", account=self.joint
        )
        graph = budget_flow(self.mode, self.period, group_by_category=True)
        assert len([node for node in graph.nodes if node.name == "Bills"]) == 1
        bill_links = [link for link in graph.links if link.kind == "bill"]
        assert {link.source for link in bill_links} == {"Personal", "Joint"}
        assert {link.target for link in bill_links} == {"Bills"}

    def test_group_by_category_defaults_to_ungrouped(self) -> None:
        Outgoing.objects.create(
            name="Netflix", amount=Decimal("15"), category=self.category, frequency="monthly", account=self.personal
        )
        Outgoing.objects.create(
            name="Spotify", amount=Decimal("10"), category=self.category, frequency="monthly", account=self.personal
        )
        graph = budget_flow(self.mode, self.period)
        names = sorted(node.name for node in graph.nodes if node.kind == "bill")
        assert names == ["Netflix", "Spotify"]


class CategoryTotalsTests(TestCase):
    def test_totals_group_and_normalise_by_category(self) -> None:
        account = Account.objects.create(name="Personal")
        bills = OutgoingCategory.objects.create(name="Bills")
        subs = OutgoingCategory.objects.create(name="Subscriptions")
        Outgoing.objects.create(
            name="Rent", amount=Decimal("800"), category=bills, frequency="monthly", account=account
        )
        Outgoing.objects.create(
            name="Council tax", amount=Decimal("1200"), category=bills, frequency="yearly", account=account
        )
        Outgoing.objects.create(
            name="Netflix", amount=Decimal("15"), category=subs, frequency="monthly", account=account
        )
        period = Period(date(2026, 7, 1), date(2026, 8, 1))
        totals = category_totals(prefetched_accounts(), Settings.BudgetMode.MONTHLY, period)

        by_name = {row.category.name: row.total for row in totals}
        assert by_name["Bills"] == Decimal("800") + Decimal("1200") / 12
        assert by_name["Subscriptions"] == Decimal("15")
        assert [row.category.name for row in totals] == ["Bills", "Subscriptions"]

    def test_category_ids_restricts_which_categories_appear(self) -> None:
        account = Account.objects.create(name="Personal")
        bills = OutgoingCategory.objects.create(name="Bills")
        subs = OutgoingCategory.objects.create(name="Subscriptions")
        Outgoing.objects.create(
            name="Rent", amount=Decimal("800"), category=bills, frequency="monthly", account=account
        )
        Outgoing.objects.create(
            name="Netflix", amount=Decimal("15"), category=subs, frequency="monthly", account=account
        )
        period = Period(date(2026, 7, 1), date(2026, 8, 1))
        totals = category_totals(prefetched_accounts(), Settings.BudgetMode.MONTHLY, period, category_ids=[bills.id])

        assert [row.category.name for row in totals] == ["Bills"]


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

    def test_one_off_only_counts_within_its_period(self) -> None:
        OneOffOutgoing.objects.create(
            name="Car service", amount=Decimal("300"), due_date=date(2026, 7, 15), account=self.account
        )
        OneOffOutgoing.objects.create(
            name="Next month's bill", amount=Decimal("500"), due_date=date(2026, 8, 15), account=self.account
        )
        summary = budget_summary(self.mode, self.period)
        assert summary.one_off_total == Decimal("300")
        assert summary.adjusted_surplus == summary.surplus - Decimal("300")

    def test_pot_contributions_reduce_unallocated_surplus(self) -> None:
        IncomeStream.objects.create(name="Salary", amount=Decimal("1000"), frequency="monthly", account=self.account)
        pot = Pot.objects.create(
            name="Holiday", target_amount=Decimal("2000"), target_date=date(2027, 1, 1), monthly_target=Decimal("100")
        )
        PotEntry.objects.create(pot=pot, period_start=date(2026, 7, 1), actual_amount=Decimal("100"))
        summary = budget_summary(self.mode, self.period)
        assert summary.pot_contributions == Decimal("100")
        assert summary.unallocated_surplus == summary.adjusted_surplus - Decimal("100")


class YearlyOutgoingTests(TestCase):
    """`recurring_month` scheduling and the three `yearly_billing` modes."""

    def setUp(self) -> None:
        self.account = Account.objects.create(name="Personal")
        self.category = OutgoingCategory.objects.create(name="Bills")

    def _yearly(self, **kwargs: object) -> Outgoing:
        defaults = {
            "name": "Insurance",
            "amount": Decimal("600"),
            "category": self.category,
            "account": self.account,
            "frequency": "yearly",
        }
        defaults.update(kwargs)
        return Outgoing.objects.create(**defaults)

    def test_scheduled_dates_places_yearly_entry_on_its_month_and_day(self) -> None:
        entry = self._yearly(recurring_day=27, recurring_month=3)
        window = (date(2026, 1, 1), date(2027, 1, 1))
        assert scheduled_dates(entry, *window) == [date(2026, 3, 27)]

    def test_scheduled_dates_applies_weekend_adjust(self) -> None:
        # 2026-08-01 is a Saturday.
        entry = self._yearly(recurring_day=1, recurring_month=8, weekend_adjust="after")
        window = (date(2026, 1, 1), date(2027, 1, 1))
        assert scheduled_dates(entry, *window) == [date(2026, 8, 3)]

    def test_scheduled_dates_clamps_29_feb_in_a_non_leap_year(self) -> None:
        entry = self._yearly(recurring_day=29, recurring_month=2)
        window = (date(2026, 1, 1), date(2027, 1, 1))  # 2026 is not a leap year.
        assert scheduled_dates(entry, *window) == [date(2026, 2, 28)]

    def test_scheduled_dates_returns_one_occurrence_per_year_in_window(self) -> None:
        entry = self._yearly(recurring_day=27, recurring_month=3)
        window = (date(2026, 1, 1), date(2028, 1, 1))
        assert scheduled_dates(entry, *window) == [date(2026, 3, 27), date(2027, 3, 27)]

    def test_scheduled_dates_empty_without_a_month(self) -> None:
        entry = self._yearly(recurring_day=27)
        window = (date(2026, 1, 1), date(2027, 1, 1))
        assert scheduled_dates(entry, *window) == []

    def test_spread_matches_plain_normalise(self) -> None:
        entry = self._yearly(recurring_day=27, recurring_month=3)
        period = Period(date(2026, 7, 1), date(2026, 8, 1))
        assert outgoing_amount(entry, "monthly", period) == normalise(entry.amount, "yearly", "monthly")

    def test_due_period_charges_full_amount_only_in_the_due_period(self) -> None:
        entry = self._yearly(recurring_day=15, recurring_month=9, yearly_billing="due_period")
        assert outgoing_amount(entry, "monthly", Period(date(2026, 8, 1), date(2026, 9, 1))) == Decimal("0")
        assert outgoing_amount(entry, "monthly", Period(date(2026, 9, 1), date(2026, 10, 1))) == Decimal("600")
        assert outgoing_amount(entry, "monthly", Period(date(2026, 10, 1), date(2026, 11, 1))) == Decimal("0")

    def test_due_period_boundary_lands_in_the_period_that_starts_on_the_due_date(self) -> None:
        entry = self._yearly(recurring_day=1, recurring_month=8, yearly_billing="due_period")
        assert outgoing_amount(entry, "monthly", Period(date(2026, 7, 1), date(2026, 8, 1))) == Decimal("0")
        assert outgoing_amount(entry, "monthly", Period(date(2026, 8, 1), date(2026, 9, 1))) == Decimal("600")

    def test_spread_to_due_divides_across_remaining_periods(self) -> None:
        entry = self._yearly(recurring_day=1, recurring_month=10, yearly_billing="spread_to_due")
        period = Period(date(2026, 7, 1), date(2026, 8, 1))
        assert outgoing_amount(entry, "monthly", period) == Decimal("200")

    def test_non_spread_billing_falls_back_to_spread_when_unscheduled(self) -> None:
        entry = self._yearly(yearly_billing="due_period")
        period = Period(date(2026, 7, 1), date(2026, 8, 1))
        assert outgoing_amount(entry, "monthly", period) == normalise(entry.amount, "yearly", "monthly")

    def test_yearly_budget_mode_charges_full_amount_under_every_billing_mode(self) -> None:
        period = Period(date(2026, 1, 1), date(2027, 1, 1))
        for billing in ("spread", "spread_to_due", "due_period"):
            entry = self._yearly(recurring_day=15, recurring_month=6, yearly_billing=billing)
            assert outgoing_amount(entry, "yearly", period) == Decimal("600")

    def test_due_period_feeds_total_outgoings(self) -> None:
        self._yearly(recurring_day=15, recurring_month=9, yearly_billing="due_period")
        summary = budget_summary("monthly", Period(date(2026, 9, 1), date(2026, 10, 1)))
        assert summary.total_outgoings == Decimal("600")
        summary = budget_summary("monthly", Period(date(2026, 8, 1), date(2026, 9, 1)))
        assert summary.total_outgoings == Decimal("0")

    def test_budget_summary_flags_yearly_bills_due_this_period_regardless_of_billing(self) -> None:
        due_this_month = self._yearly(name="Insurance", recurring_day=15, recurring_month=9)
        self._yearly(name="Next year's TV licence", recurring_day=15, recurring_month=10)
        summary = budget_summary("monthly", Period(date(2026, 9, 1), date(2026, 10, 1)))
        assert summary.yearly_due == [due_this_month]

    def test_accounts_page_flags_outgoing_due_in_the_current_active_period(self) -> None:
        settings = Settings.get()
        period = active_period(settings.budget_mode, settings.budget_start_day)
        due_now = self._yearly(name="Insurance", recurring_day=period.start.day, recurring_month=period.start.month)
        due_later = self._yearly(
            name="Warranty", recurring_day=period.start.day, recurring_month=(period.start.month % 12) + 1
        )
        response = self.client.get(reverse("budget:accounts"))
        summary = next(s for s in response.context["account_summaries"] if s.account.id == self.account.id)
        outgoings = {o.id: o for o in summary.account.outgoings.all()}
        assert outgoings[due_now.id].due_this_period is True
        assert outgoings[due_later.id].due_this_period is False


class OutgoingPotCoverageTests(TestCase):
    """Pot-linked yearly outgoings get a computed `.pot_covered` / `.pot_saved` via
    `_accounts_context`, mirroring `OneOffPotCoverageTests` for one-offs."""

    def setUp(self) -> None:
        self.account = Account.objects.create(name="Personal")
        self.category = OutgoingCategory.objects.create(name="Bills")
        self.pot = Pot.objects.create(
            name="Insurance fund",
            target_amount=Decimal("600"),
            target_date=date(2027, 1, 1),
            monthly_target=Decimal("50"),
        )

    def _outgoing(self) -> Outgoing:
        response = self.client.get(reverse("budget:accounts"))
        assert response.status_code == 200
        summary = next(s for s in response.context["account_summaries"] if s.account.id == self.account.id)
        return next(iter(summary.account.outgoings.all()))

    def test_covered_when_pot_balance_meets_amount(self) -> None:
        PotEntry.objects.create(pot=self.pot, period_start=date(2026, 7, 1), actual_amount=Decimal("600"))
        Outgoing.objects.create(
            name="Insurance",
            amount=Decimal("600"),
            category=self.category,
            account=self.account,
            frequency="yearly",
            recurring_day=15,
            recurring_month=9,
            yearly_billing="due_period",
        )
        self.pot.linked_outgoing = Outgoing.objects.get(name="Insurance")
        self.pot.save()
        outgoing = self._outgoing()
        assert outgoing.pot_saved == Decimal("600")
        assert outgoing.pot_covered is True

    def test_uncovered_when_pot_balance_below_amount(self) -> None:
        PotEntry.objects.create(pot=self.pot, period_start=date(2026, 7, 1), actual_amount=Decimal("100"))
        outgoing = Outgoing.objects.create(
            name="Insurance",
            amount=Decimal("600"),
            category=self.category,
            account=self.account,
            frequency="yearly",
            recurring_day=15,
            recurring_month=9,
            yearly_billing="due_period",
        )
        self.pot.linked_outgoing = outgoing
        self.pot.save()
        result = self._outgoing()
        assert result.pot_saved == Decimal("100")
        assert result.pot_covered is False

    def test_unlinked_outgoing_has_no_coverage(self) -> None:
        Outgoing.objects.create(
            name="Insurance", amount=Decimal("600"), category=self.category, account=self.account, frequency="yearly"
        )
        outgoing = self._outgoing()
        assert outgoing.pot_covered is None


class UpcomingYearlyBillsTests(TestCase):
    """Dashboard heads-up: yearly bills due this month or in the next few."""

    def setUp(self) -> None:
        self.account = Account.objects.create(name="Personal")
        self.category = OutgoingCategory.objects.create(name="Bills")
        self.today = date(2026, 6, 15)

    def _yearly(self, **kwargs: object) -> Outgoing:
        defaults = {
            "name": "Bill",
            "amount": Decimal("600"),
            "category": self.category,
            "account": self.account,
            "frequency": "yearly",
        }
        defaults.update(kwargs)
        return Outgoing.objects.create(**defaults)

    def test_annotates_due_date_and_months_away_within_the_default_window(self) -> None:
        this_month = self._yearly(name="Insurance", recurring_day=20, recurring_month=6)
        next_month = self._yearly(name="MOT", recurring_day=1, recurring_month=7)
        in_three = self._yearly(name="TV Licence", recurring_day=1, recurring_month=9)

        bills = upcoming_yearly_bills(prefetched_accounts(), self.today)

        assert [b.id for b in bills] == [this_month.id, next_month.id, in_three.id]
        assert bills[0].due_date == date(2026, 6, 20)
        assert bills[0].months_away == 0
        assert bills[1].months_away == 1
        assert bills[2].months_away == 3

    def test_excludes_bills_beyond_the_window_and_already_passed_this_year(self) -> None:
        self._yearly(name="Too far out", recurring_day=1, recurring_month=10)  # 4 months away
        self._yearly(name="Already happened", recurring_day=1, recurring_month=6)  # rolls to next year
        self._yearly(name="Not scheduled")  # no recurring_month
        Outgoing.objects.create(
            name="Monthly rent", amount=Decimal("1000"), category=self.category, account=self.account
        )  # not yearly

        assert upcoming_yearly_bills(prefetched_accounts(), self.today) == []

    def test_months_ahead_is_configurable(self) -> None:
        self._yearly(name="TV Licence", recurring_day=1, recurring_month=9)  # 3 months away
        assert upcoming_yearly_bills(prefetched_accounts(), self.today, months_ahead=2) == []


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

    def test_split_equalises_take_home_when_personal_outgoings_differ(self) -> None:
        # Weighting by raw salary alone would leave a gap between A's and B's
        # final take-home equal to the difference in their personal
        # outgoings; weighting by disposable income (salary minus personal
        # outgoings) closes that gap so both take-homes land exactly equal.
        Outgoing.objects.create(
            name="A Phone", amount=Decimal("6.90"), category=self.category, frequency="monthly", account=self.a
        )
        Outgoing.objects.create(
            name="B Phone", amount=Decimal("8.40"), category=self.category, frequency="monthly", account=self.b
        )
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
        assert amounts[a_to_spends.id] == amounts[b_to_spends.id] == Decimal("1492.35")
        assert amounts[a_to_joint.id] == Decimal("1500.75")
        assert amounts[b_to_joint.id] == Decimal("499.25")


class TransferPlanTests(TestCase):
    """transfer_plan() is a thin grouping wrapper around
    resolve_transfer_amounts — this locks down the grouping/subtotals plus
    the schedule and note fields the wrapper adds on top."""

    def setUp(self) -> None:
        self.mode = Settings.BudgetMode.MONTHLY
        self.period = Period(date(2026, 7, 1), date(2026, 8, 1))
        self.category = OutgoingCategory.objects.create(name="Bills")
        self.a = Account.objects.create(name="A Personal")
        self.b = Account.objects.create(name="B Personal")
        self.joint = Account.objects.create(name="Joint", account_type="joint")
        IncomeStream.objects.create(name="A Salary", amount=Decimal("3000"), frequency="monthly", account=self.a)
        IncomeStream.objects.create(name="B Salary", amount=Decimal("2000"), frequency="monthly", account=self.b)
        Outgoing.objects.create(
            name="Joint bills",
            amount=Decimal("1500"),
            category=self.category,
            frequency="monthly",
            account=self.joint,
        )

    def _plan(self) -> list:
        return transfer_plan(prefetched_accounts(), self.mode, self.period)

    def test_one_row_per_transfer_grouped_by_source(self) -> None:
        Transfer.objects.create(
            name="A standing order",
            from_account=self.a,
            to_account=self.joint,
            amount=Decimal("750"),
            frequency="monthly",
            recurring_day=28,
        )
        Transfer.objects.create(
            name="B standing order",
            from_account=self.b,
            to_account=self.joint,
            amount=Decimal("750"),
            frequency="monthly",
            recurring_day=28,
        )
        groups = self._plan()
        assert len(groups) == 2
        assert {g.account.id for g in groups} == {self.a.id, self.b.id}
        for group in groups:
            assert len(group.rows) == 1
            assert group.total == group.rows[0].amount == Decimal("750")
            assert group.rows[0].pay_date == date(2026, 7, 28)
            assert group.rows[0].note == ""

    def test_matches_resolve_transfer_amounts(self) -> None:
        a_to_joint = Transfer.objects.create(
            name="A to joint", from_account=self.a, to_account=self.joint, calc_method=Transfer.CalcMethod.SPLIT
        )
        b_to_joint = Transfer.objects.create(
            name="B to joint", from_account=self.b, to_account=self.joint, calc_method=Transfer.CalcMethod.SPLIT
        )
        accounts = prefetched_accounts()
        expected = resolve_transfer_amounts(accounts, self.mode, self.period)
        actual = {row.transfer.id: row.amount for group in self._plan() for row in group.rows}
        assert actual == {a_to_joint.id: expected[a_to_joint.id], b_to_joint.id: expected[b_to_joint.id]}

    def test_split_note_names_the_destination_shortfall(self) -> None:
        a_to_joint = Transfer.objects.create(
            name="A to joint", from_account=self.a, to_account=self.joint, calc_method=Transfer.CalcMethod.SPLIT
        )
        Transfer.objects.create(
            name="B to joint", from_account=self.b, to_account=self.joint, calc_method=Transfer.CalcMethod.SPLIT
        )
        row = next(r for g in self._plan() for r in g.rows if r.transfer.id == a_to_joint.id)
        assert "Joint" in row.note
        assert "1500.00" in row.note


class MoneyToMovePlacementTests(TestCase):
    """Money to move lives on the Overview page (bottom), not Accounts —
    moved there after the accounts page got too cluttered with it."""

    def setUp(self) -> None:
        source = Account.objects.create(name="Personal")
        destination = Account.objects.create(name="Joint")
        Transfer.objects.create(
            name="Contribution", from_account=source, to_account=destination, amount=Decimal("500"), frequency="monthly"
        )

    def test_overview_page_carries_transfer_groups(self) -> None:
        response = self.client.get(reverse("budget:overview"))
        assert response.status_code == 200
        assert len(response.context["transfer_groups"]) == 1

    def test_accounts_page_does_not_carry_transfer_groups(self) -> None:
        response = self.client.get(reverse("budget:accounts"))
        assert response.status_code == 200
        assert "transfer_groups" not in response.context


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

    def test_htmx_response_carries_the_success_message_oob(self) -> None:
        """Issue #13: the partial itself must render the message, not just queue it."""
        url = reverse("budget:log_pot_entry", args=[self.pot.id])
        response = self.client.post(url, {"actual_amount": "150"}, HTTP_HX_REQUEST="true")
        content = response.content.decode()
        assert "hx-swap-oob" in content
        assert f"Logged saved amount for {self.pot.name}." in content

    def test_message_does_not_leak_onto_the_next_full_page(self) -> None:
        url = reverse("budget:log_pot_entry", args=[self.pot.id])
        self.client.post(url, {"actual_amount": "150"}, HTTP_HX_REQUEST="true")
        response = self.client.get(reverse("budget:accounts"))
        assert f"Logged saved amount for {self.pot.name}." not in response.content.decode()


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


class AccountsAccountFilterTests(TestCase):
    """The category filter moved to the Outgoings page (issue #10); Accounts got
    an account filter in its place, matching Overview/Timeline/Flow."""

    def test_accounts_param_narrows_rendered_cards(self) -> None:
        # HX request, so the response is just the account-card partial — the
        # full page's own filter form lists every account's name regardless
        # of selection, which would otherwise collide with this assertion.
        personal = Account.objects.create(name="Personal")
        Account.objects.create(name="Joint")

        response = self.client.get(reverse("budget:accounts"), {"accounts": [personal.id]}, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        assert b"Personal" in response.content
        assert b"Joint" not in response.content

    def test_no_accounts_param_shows_everything(self) -> None:
        Account.objects.create(name="Personal")
        Account.objects.create(name="Joint")

        response = self.client.get(reverse("budget:accounts"))

        assert b"Personal" in response.content
        assert b"Joint" in response.content


class OutgoingRowsTests(TestCase):
    def test_one_off_inside_period_is_included_and_outside_is_not(self) -> None:
        account = Account.objects.create(name="Personal")
        settings = Settings.get()
        period = active_period(settings.budget_mode, settings.budget_start_day)
        OneOffOutgoing.objects.create(name="In period", amount=Decimal("50"), due_date=period.start, account=account)
        OneOffOutgoing.objects.create(name="Outside period", amount=Decimal("50"), due_date=period.end, account=account)

        rows = outgoing_rows(settings.budget_mode, period)

        names = {row.name for row in rows}
        assert "In period" in names
        assert "Outside period" not in names

    def test_yearly_period_amount_matches_outgoing_amount_not_raw_amount(self) -> None:
        account = Account.objects.create(name="Personal")
        category = OutgoingCategory.objects.create(name="Bills")
        outgoing = Outgoing.objects.create(
            name="Insurance",
            amount=Decimal("1200"),
            category=category,
            frequency="yearly",
            yearly_billing=Outgoing.YearlyBilling.DUE_PERIOD,
            recurring_day=1,
            recurring_month=1,
            account=account,
        )
        settings = Settings.get()
        period = active_period(settings.budget_mode, settings.budget_start_day)

        rows = outgoing_rows(settings.budget_mode, period)

        row = next(r for r in rows if r.pk == outgoing.id)
        assert row.period_amount == outgoing_amount(outgoing, settings.budget_mode, period)

    def test_category_filter_drops_one_offs(self) -> None:
        account = Account.objects.create(name="Personal")
        bills = OutgoingCategory.objects.create(name="Bills")
        settings = Settings.get()
        period = active_period(settings.budget_mode, settings.budget_start_day)
        OneOffOutgoing.objects.create(name="One-off", amount=Decimal("50"), due_date=period.start, account=account)

        rows = outgoing_rows(settings.budget_mode, period, category_ids=[bills.id])

        assert rows == []


class OutgoingSortTests(TestCase):
    def test_default_sort_is_amount_descending(self) -> None:
        account = Account.objects.create(name="Personal")
        category = OutgoingCategory.objects.create(name="Bills")
        Outgoing.objects.create(
            name="Small", amount=Decimal("10"), category=category, frequency="monthly", account=account
        )
        Outgoing.objects.create(
            name="Big", amount=Decimal("500"), category=category, frequency="monthly", account=account
        )
        settings = Settings.get()
        period = active_period(settings.budget_mode, settings.budget_start_day)
        rows = outgoing_rows(settings.budget_mode, period)

        sorted_rows, col, direction = sort_outgoing_rows(rows, None, None)

        assert col == "amount"
        assert direction == "desc"
        assert [r.name for r in sorted_rows] == ["Big", "Small"]

    def test_invalid_sort_falls_back_to_default(self) -> None:
        _, col, direction = sort_outgoing_rows([], "not-a-column", "sideways")
        assert col == "amount"
        assert direction == "desc"


class OutgoingListViewTests(TestCase):
    def test_page_renders(self) -> None:
        response = self.client.get(reverse("budget:outgoings"))
        assert response.status_code == 200

    def test_hx_request_returns_partial(self) -> None:
        response = self.client.get(reverse("budget:outgoings"), HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        self.assertTemplateUsed(response, "budget/_outgoings.html")
        self.assertTemplateNotUsed(response, "budget/outgoings.html")

    def test_accounts_param_narrows_rows(self) -> None:
        personal = Account.objects.create(name="Personal")
        joint = Account.objects.create(name="Joint")
        category = OutgoingCategory.objects.create(name="Bills")
        Outgoing.objects.create(
            name="Rent", amount=Decimal("800"), category=category, frequency="monthly", account=personal
        )
        Outgoing.objects.create(
            name="Mortgage", amount=Decimal("1200"), category=category, frequency="monthly", account=joint
        )

        response = self.client.get(reverse("budget:outgoings"), {"accounts": [personal.id]})

        assert b"Rent" in response.content
        assert b"Mortgage" not in response.content

    def test_categories_param_narrows_rows(self) -> None:
        account = Account.objects.create(name="Personal")
        bills = OutgoingCategory.objects.create(name="Bills")
        subs = OutgoingCategory.objects.create(name="Subscriptions")
        Outgoing.objects.create(
            name="Rent", amount=Decimal("800"), category=bills, frequency="monthly", account=account
        )
        Outgoing.objects.create(
            name="Netflix", amount=Decimal("15"), category=subs, frequency="monthly", account=account
        )

        response = self.client.get(reverse("budget:outgoings"), {"categories": [bills.id]})

        assert b"Rent" in response.content
        assert b"Netflix" not in response.content


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


class TimelineLabelStackingTests(TestCase):
    """Regression: same-day timeline stops used to render labels on top of
    each other (only every-other stop flipped above/below)."""

    def test_overlapping_labels_get_distinct_vertical_slots(self) -> None:
        # Three same-x, wide labels can't share any of the first two slots.
        dys = _assign_label_dys([(100, 60), (100, 60), (100, 60)])
        assert len(set(dys)) == 3

    def test_non_overlapping_labels_reuse_the_first_slot(self) -> None:
        dys = _assign_label_dys([(0, 20), (900, 20)])
        assert dys == [-12, -12]

    def test_labels_beyond_the_slot_cap_get_no_label(self) -> None:
        # 5 same-x labels: only the first 3 (the cap) get a slot, the rest render no label.
        dys = _assign_label_dys([(100, 60)] * 5)
        assert all(dy is not None for dy in dys[:3])
        assert dys[3:] == [None, None]


class TimelineClusteringTests(TestCase):
    """Regression: dense same-day entries used to render one overlapping,
    indistinguishable circle+label per stop instead of a single marker."""

    def setUp(self) -> None:
        self.account = Account.objects.create(name="Personal")

    def test_same_day_stops_collapse_into_one_badged_cluster(self) -> None:
        stops = []
        balance = Decimal("0")
        for i in range(6):
            balance -= Decimal("50")
            stops.append(TimelineStop(date(2026, 7, 1), f"Bill {i}", Decimal("-50"), "outgoing", balance))
        lane = AccountLane(account=self.account, stops=stops, end_balance=balance)

        svg = _timeline_svg([lane], date(2026, 7, 1), date(2026, 8, 1), "£")
        clusters = svg["lanes"][0]["clusters"]

        assert len(clusters) == 1
        cluster = clusters[0]
        assert cluster["count"] == 6
        assert cluster["balance_str"] == f"{balance:.2f}"

        details = svg["cluster_details"][cluster["id"]]
        assert len(details["entries"]) == 6
        assert details["entries"][0]["label"] == "Bill 0"

    def test_different_days_stay_as_separate_clusters(self) -> None:
        stops = [
            TimelineStop(date(2026, 7, 1), "Salary", Decimal("1000"), "income", Decimal("1000")),
            TimelineStop(date(2026, 7, 15), "Rent", Decimal("-400"), "outgoing", Decimal("600")),
        ]
        lane = AccountLane(account=self.account, stops=stops, end_balance=Decimal("600"))

        svg = _timeline_svg([lane], date(2026, 7, 1), date(2026, 8, 1), "£")
        clusters = svg["lanes"][0]["clusters"]

        assert len(clusters) == 2
        assert all(c["count"] == 1 for c in clusters)

    def test_each_account_gets_its_own_svg_and_detail_panel(self) -> None:
        other = Account.objects.create(name="Other")
        lanes = [
            AccountLane(account=self.account, stops=[], end_balance=Decimal("0")),
            AccountLane(account=other, stops=[], end_balance=Decimal("0")),
        ]
        svg = _timeline_svg(lanes, date(2026, 7, 1), date(2026, 8, 1), "£")
        assert [lane["account"].id for lane in svg["lanes"]] == [self.account.id, other.id]
        assert svg["lanes"][0]["hover_id"] != svg["lanes"][1]["hover_id"]

    def test_dense_timeline_page_renders_cluster_details(self) -> None:
        category = OutgoingCategory.objects.create(name="Bills")
        for i in range(5):
            Outgoing.objects.create(
                name=f"Bill {i}",
                amount=Decimal("50"),
                category=category,
                account=self.account,
                frequency="monthly",
                recurring_day=1,
            )

        response = self.client.get(reverse("budget:timeline"))

        assert response.status_code == 200
        assert b"timeline-clusters" in response.content


class DetailViewSmokeTests(TestCase):
    """One 200-plus-key-context check per model's new detail page (issue #8)."""

    def setUp(self) -> None:
        self.account = Account.objects.create(name="Personal")
        self.other = Account.objects.create(name="Joint")
        self.category = OutgoingCategory.objects.create(name="Bills")

    def test_account_detail_returns_summary(self) -> None:
        IncomeStream.objects.create(name="Salary", amount=Decimal("3000"), frequency="monthly", account=self.account)
        response = self.client.get(reverse("budget:account_detail", args=[self.account.id]))
        assert response.status_code == 200
        assert response.context["summary"].account == self.account
        assert response.context["summary"].income == Decimal("3000")

    def test_income_detail_returns_upcoming_dates(self) -> None:
        income = IncomeStream.objects.create(
            name="Salary", amount=Decimal("3000"), frequency="monthly", recurring_day=25, account=self.account
        )
        response = self.client.get(reverse("budget:income_detail", args=[income.id]))
        assert response.status_code == 200
        assert response.context["income"] == income
        assert response.context["upcoming_dates"]

    def test_outgoing_detail_returns_upcoming_dates(self) -> None:
        outgoing = Outgoing.objects.create(
            name="Rent",
            amount=Decimal("800"),
            category=self.category,
            account=self.account,
            frequency="monthly",
            recurring_day=1,
        )
        response = self.client.get(reverse("budget:outgoing_detail", args=[outgoing.id]))
        assert response.status_code == 200
        assert response.context["outgoing"] == outgoing
        assert response.context["upcoming_dates"]

    def test_transfer_detail_returns_effective_amount(self) -> None:
        transfer = Transfer.objects.create(
            name="Joint contribution",
            from_account=self.account,
            to_account=self.other,
            amount=Decimal("200"),
            frequency="monthly",
        )
        response = self.client.get(reverse("budget:transfer_detail", args=[transfer.id]))
        assert response.status_code == 200
        assert response.context["transfer"] == transfer
        assert response.context["effective_amount"] == Decimal("200")

    def test_oneoff_detail_returns_pot_coverage(self) -> None:
        pot = Pot.objects.create(
            name="Car fund", target_amount=Decimal("1000"), target_date=date(2027, 1, 1), monthly_target=Decimal("50")
        )
        PotEntry.objects.create(pot=pot, period_start=date(2026, 7, 1), actual_amount=Decimal("300"))
        oneoff = OneOffOutgoing.objects.create(
            name="Car service", amount=Decimal("250"), due_date=date(2026, 9, 1), account=self.account, linked_pot=pot
        )
        response = self.client.get(reverse("budget:oneoff_detail", args=[oneoff.id]))
        assert response.status_code == 200
        assert response.context["oneoff"] == oneoff
        assert response.context["pot_covered"] is True
        assert response.context["pot_saved"] == Decimal("300")

    def test_pot_detail_returns_progress_and_contribution_history(self) -> None:
        pot = Pot.objects.create(
            name="Holiday", target_amount=Decimal("1200"), target_date=date(2027, 1, 1), monthly_target=Decimal("100")
        )
        PotEntry.objects.create(pot=pot, period_start=date(2026, 5, 1), actual_amount=Decimal("50"))
        PotEntry.objects.create(pot=pot, period_start=date(2026, 6, 1), actual_amount=Decimal("75"))

        response = self.client.get(reverse("budget:pot_detail", args=[pot.id]))

        assert response.status_code == 200
        assert response.context["progress"].pot == pot
        content = response.content.decode()
        assert "50.00" in content
        assert "75.00" in content

    def test_account_detail_split_transfer_amount_matches_accounts_page(self) -> None:
        """Guards resolving transfer_amounts across all accounts on the detail
        page, not just this account — required for split/surplus transfers.

        Expected value comes straight from `resolve_transfer_amounts` (the accounts
        page itself no longer annotates transfers with `.effective_amount` — it
        stopped listing them per-account, see issue #10 — so it can't serve as the
        oracle here any more)."""
        IncomeStream.objects.create(name="A Salary", amount=Decimal("3000"), frequency="monthly", account=self.account)
        IncomeStream.objects.create(name="B Salary", amount=Decimal("2000"), frequency="monthly", account=self.other)
        Outgoing.objects.create(
            name="Joint bills",
            amount=Decimal("1000"),
            category=self.category,
            frequency="monthly",
            account=self.other,
        )
        a_to_joint = Transfer.objects.create(
            name="A to joint", from_account=self.account, to_account=self.other, calc_method=Transfer.CalcMethod.SPLIT
        )

        settings = Settings.get()
        period = active_period(settings.budget_mode, settings.budget_start_day)
        expected = resolve_transfer_amounts(prefetched_accounts(), settings.budget_mode, period)[a_to_joint.id]

        detail_response = self.client.get(reverse("budget:account_detail", args=[self.account.id]))
        actual = next(
            t.effective_amount for t in detail_response.context["account"].transfers_out.all() if t.id == a_to_joint.id
        )
        assert actual == expected


class DetailPageLinkTests(TestCase):
    """List pages link into the new detail pages (issue #8)."""

    def test_accounts_page_links_to_account_detail(self) -> None:
        account = Account.objects.create(name="Personal")
        response = self.client.get(reverse("budget:accounts"))
        assert reverse("budget:account_detail", args=[account.id]).encode() in response.content

    def test_pots_page_links_to_pot_detail(self) -> None:
        pot = Pot.objects.create(
            name="Holiday", target_amount=Decimal("1200"), target_date=date(2027, 1, 1), monthly_target=Decimal("100")
        )
        response = self.client.get(reverse("budget:pots"))
        assert reverse("budget:pot_detail", args=[pot.id]).encode() in response.content


class FormRedirectTests(TestCase):
    """Create/Update should land on the object's detail page via get_absolute_url(),
    not always on the accounts/pots list — except OutgoingCategory, which has no
    detail page and keeps redirecting to the accounts list."""

    def test_account_create_redirects_to_detail_page(self) -> None:
        response = self.client.post(reverse("budget:account_add"), {"name": "Savings", "account_type": "savings"})
        account = Account.objects.get(name="Savings")
        self.assertRedirects(response, reverse("budget:account_detail", args=[account.id]))

    def test_pot_create_redirects_to_detail_page(self) -> None:
        response = self.client.post(
            reverse("budget:pot_add"),
            {"name": "Holiday 2026", "target_amount": "2000", "target_date": "2026-12-01", "monthly_target": "100"},
        )
        pot = Pot.objects.get(name="Holiday 2026")
        self.assertRedirects(response, reverse("budget:pot_detail", args=[pot.id]))

    def test_pot_create_next_param_still_overrides_detail_redirect(self) -> None:
        response = self.client.post(
            reverse("budget:pot_add") + "?next=/budget/pots/",
            {"name": "Holiday 2027", "target_amount": "2000", "target_date": "2027-12-01", "monthly_target": "100"},
        )
        self.assertRedirects(response, "/budget/pots/")

    def test_category_create_still_redirects_to_accounts_list(self) -> None:
        response = self.client.post(reverse("budget:category_add"), {"name": "Groceries"})
        self.assertRedirects(response, reverse("budget:accounts"))
