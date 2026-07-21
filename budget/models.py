"""Budget domain models.

Hierarchy:
  Account
    ├─ IncomeStream  (income landing in this account)
    ├─ Outgoing      (recurring expense from this account)
    │    └─ OutgoingVariance  (actual vs budgeted for a period)
    ├─ OneOffOutgoing (future-dated single payment)
    └─ Transfer (from_account → to_account)

  Pot  (savings goal; optionally linked to Project / OneOffOutgoing)
    └─ PotEntry  (actual amount saved in a given period)
"""

from decimal import Decimal

from django.db import models


class FrequencyMixin(models.Model):
    """Abstract mixin providing the shared `frequency` field and the actual
    payment-date scheduling fields (day-of-month/weekday, weekend adjustment,
    and weekly interval/anchor for fortnightly-or-longer schedules).

    These fields drive display and calendar placement only — budget totals
    are still computed purely from `frequency` (see `services.normalise`).
    """

    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    class WeekendAdjust(models.TextChoices):
        BEFORE = "before", "Move to Friday before"
        AFTER = "after", "Move to Monday after"

    frequency = models.CharField(max_length=10, choices=Frequency, default=Frequency.MONTHLY)
    recurring_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Day of month (1-31) for monthly/yearly; day of week (1=Mon...7=Sun) for "
            "weekly. Blank = unscheduled (won't appear on the calendar)."
        ),
    )
    weekend_adjust = models.CharField(
        max_length=6,
        choices=WeekendAdjust,
        blank=True,
        help_text="Monthly/yearly only: shift the day if it lands on a weekend. Blank = leave it on the weekend.",
    )
    week_interval = models.PositiveSmallIntegerField(
        default=1,
        null=True,
        blank=True,
        help_text="Weekly only: every N weeks (2 = fortnightly). Blank behaves as 1 (every week).",
    )
    week_anchor = models.DateField(
        null=True,
        blank=True,
        help_text="Weekly only, needed when interval > 1: a date the payment occurs on, to anchor which weeks.",
    )

    class Meta:
        abstract = True


class Account(models.Model):
    class AccountType(models.TextChoices):
        PERSONAL = "personal", "Personal"
        JOINT = "joint", "Joint"
        SAVINGS = "savings", "Savings"
        OTHER = "other", "Other"

    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=10, choices=AccountType, default=AccountType.PERSONAL)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class IncomeStream(FrequencyMixin):
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="income_streams")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.account})"


class Transfer(FrequencyMixin):
    """A recurring account-to-account transfer.

    `calc_method` controls how the per-period amount is derived:
      - fixed:   `amount` normalised by `frequency`, as before.
      - split:   this account's salary-ratio share of `to_account`'s funding
                 need, split across all `split` transfers into the same account.
      - surplus: whatever is left in `from_account` after everything else.

    For `split`/`surplus`, `amount` is unused (the engine computes it fresh
    each period — see `services.resolve_transfer_amounts`); `frequency` and
    the scheduling fields still place it on the calendar/timeline.
    """

    class CalcMethod(models.TextChoices):
        FIXED = "fixed", "Fixed amount"
        SPLIT = "split", "Salary-ratio split of destination's need"
        SURPLUS = "surplus", "Sweep source account's surplus"

    name = models.CharField(max_length=200)
    from_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transfers_out")
    to_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transfers_in")
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    calc_method = models.CharField(max_length=10, choices=CalcMethod, default=CalcMethod.FIXED)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name}: {self.from_account} → {self.to_account}"


class OutgoingCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "outgoing categories"

    def __str__(self) -> str:
        return self.name


class Outgoing(FrequencyMixin):
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.ForeignKey(OutgoingCategory, on_delete=models.PROTECT, related_name="outgoings")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="outgoings")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.category})"


class OutgoingVariance(models.Model):
    """Records the actual amount spent against a recurring outgoing for one period."""

    outgoing = models.ForeignKey(Outgoing, on_delete=models.CASCADE, related_name="variances")
    period_start = models.DateField()
    actual_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = [("outgoing", "period_start")]
        ordering = ["-period_start"]

    def __str__(self) -> str:
        return f"{self.outgoing} @ {self.period_start}"

    @property
    def delta(self) -> Decimal:
        """Positive = overspent, negative = underspent."""
        return self.actual_amount - self.outgoing.amount


class OneOffOutgoing(models.Model):
    """A single future-dated payment.

    `linked_pot` is set after Pot is defined; Django resolves the string reference.
    """

    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="one_off_outgoings")
    linked_pot = models.ForeignKey(
        "Pot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="one_off_outgoings",
    )

    class Meta:
        ordering = ["due_date"]

    def __str__(self) -> str:
        return f"{self.name} (due {self.due_date})"


class Pot(models.Model):
    """A named savings goal with a target amount and deadline."""

    name = models.CharField(max_length=200)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    target_date = models.DateField()
    monthly_target = models.DecimalField(max_digits=12, decimal_places=2)
    linked_project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pots",
    )
    linked_one_off = models.ForeignKey(
        OneOffOutgoing,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pots",
    )

    class Meta:
        ordering = ["target_date", "name"]

    def __str__(self) -> str:
        return self.name


class PotEntry(models.Model):
    """Records the actual amount saved into a Pot in a given period."""

    pot = models.ForeignKey(Pot, on_delete=models.CASCADE, related_name="entries")
    period_start = models.DateField()
    actual_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = [("pot", "period_start")]
        ordering = ["-period_start"]

    def __str__(self) -> str:
        return f"{self.pot} @ {self.period_start}"
