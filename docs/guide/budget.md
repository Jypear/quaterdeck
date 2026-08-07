# Budget & pots

The Budget section has five tabs: **Overview, Accounts, Pots, Timeline, Flow**.

## Accounts

Everything else in Budget is scoped to accounts, so set these up first (Budget →
Accounts). An account is just a name and a type (personal / joint / savings / other) —
no balance or bank connection, since Quaterdeck doesn't sync with real bank data. Income
streams, outgoings, transfers, and one-off payments are each assigned to one account.
Accounts can be selected individually or all together, on every view that supports it,
so you can look at "just my personal account" or "the whole household" without any
grouping/percentage config to maintain.

## Income

Named income streams (salary, dividends, freelance, a partner's salary, …), each with an
amount, a frequency (weekly/monthly/yearly), and the account it lands in. Multiple
streams per account are fine — a joint account might have both partners' contributions
listed separately.

## Outgoings

Recurring expenses (rent, subscriptions, groceries), each with a name, budgeted amount,
category, frequency, and account. Categories are user-defined — create as many as you
need (Budget → Accounts → outgoing categories) to group things your way.

**Logging actual spend.** Outgoings are budgeted amounts, not automatic bank feeds — each
period you can log what you *actually* spent against an outgoing right from the Accounts
page. Resubmitting a logged amount for the same period corrects it rather than creating a
duplicate. The difference (actual − budgeted) is that outgoing's **variance**, and it
flows straight into the surplus calculation for that period — overspending on groceries
this month reduces what's left over, even though the budgeted figure didn't change.

## Transfers

Inter-account transfers are first-class entries, not outgoings — they move money from
one account to another and are visible from both ends. Each has a name, a
`from_account`/`to_account` pair, a frequency, and one of three calculation methods:

- **Fixed amount** — a plain configured amount, normalised like any outgoing.
- **Salary-ratio split** — for transfers that jointly fund one destination account (e.g.
  two partners both topping up a joint account), this automatically works out each
  contributor's fair share of the shortfall, weighted by what each person actually has
  left over after their *own* outgoings — not just by raw salary. So if one partner has
  heavier personal costs, the split adjusts to still leave both of you with an equal
  amount spare, rather than being a flat 50/50 or salary-proportional cut.
- **Sweep source surplus** — takes whatever's left in the source account after
  everything else for the period, so a "sweep leftover into savings" transfer doesn't
  need a fixed number at all.

## One-off outgoings

Future-dated single payments (a car service due in November, an annual insurance
renewal) that only show up in the budget period they actually fall in — they don't
clutter every period like a recurring outgoing would. A one-off can optionally be linked
to a pot, so you can save toward it in advance; once linked, the Accounts page shows a
covered/uncovered badge comparing the pot's saved balance against the payment amount.

## Overview: the budget summary

The Overview tab totals income vs. outgoings (and transfers) for the selected period —
across all accounts, or per-account — and shows the **surplus**: what's left after
everything recurring is accounted for, then an **adjusted surplus** that also factors in
this period's logged variances. Unallocated surplus is called out deliberately, as a
nudge toward putting it in a pot — the app never allocates it for you.

## Pots

Pots are savings goals: a name, a target amount, a target date, and a monthly
contribution target. Each period, you log what you actually saved into a pot (same
overwrite-on-resubmit behaviour as outgoing variance logging). From that, the app tracks
status:

- **Ahead** — you've saved more than expected to date.
- **On track** — saved matches expected.
- **Behind** — saved is short of expected; the app shows the new per-remaining-period
  amount needed to still hit the target by its deadline, with a one-click **"Set monthly
  target to £X"** button if you want to accept the adjustment. Ignoring the nudge needs
  no action — it's a suggestion, never enforced.

A pot can optionally link to a **Project** or to a **one-off outgoing** (see above).

## Timeline

A visual, per-account lane of every dated "stop" (income, outgoing, transfer) across the
current period, running balance included — useful for seeing at a glance *when* in the
period money moves, not just the totals. Same-day entries in one account collapse into a
single marker badged with a count; click or tab to a marker to list that day's entries and
resulting balance below the chart.

## Flow

A Sankey-style diagram of where money moves between accounts for the period — income in,
outgoings out, transfers between accounts — as a single picture rather than a table.
