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

Every account, income stream, outgoing, transfer, and one-off name is a link through to
its own detail page — the account page shows this period's summary and its full list of
entries; income/outgoing/transfer/one-off pages show their upcoming scheduled payment
dates.

## Income

Named income streams (salary, dividends, freelance, a partner's salary, …), each with an
amount, a frequency (weekly/monthly/yearly), and the account it lands in. Multiple
streams per account are fine — a joint account might have both partners' contributions
listed separately.

Salaries change most months, and a salary change is exactly what moves a split/surplus
transfer's amount — so the Dashboard's income list is click-to-edit: click an amount,
type the new figure, and the whole money panel (transfers, chart, hero totals) updates
immediately without a page reload.

## Outgoings

Recurring expenses (rent, subscriptions, groceries), each with a name, budgeted amount,
category, frequency, and account. Categories are user-defined — create and edit them
from the Categories strip on the Accounts page (or via the account page's add menu).
Each outgoing shows its category as a badge on its row; the Outgoings tab's filter row
lets you tick/untick categories to narrow which outgoings are shown and see a **By
category** total for the active period. The Flow tab can also group bills by category
instead of listing each one individually (see below).

**Yearly outgoings.** A yearly outgoing can be given a due month and day (e.g. an
insurance renewal due 27 March), which also places it on the calendar and timeline. How
its amount lands in the budget is controlled per-outgoing by **yearly billing**:

- **Spread evenly** (the default) — the annual amount divided flatly across every
  period, same as today. Existing yearly outgoings keep this behaviour until you change
  it.
- **Spread to due date** — divided across only the periods remaining until the next due
  date, so the per-period figure grows the closer the bill gets rather than staying flat
  all year.
- **Due period only** — nothing until the period the bill is actually due, then the full
  amount, counted as a normal outgoing (so it shows in that period's headline
  outgoings/surplus figures rather than off to the side).

A yearly outgoing left without a due day/month keeps spreading evenly regardless of which
billing mode is selected — there's nowhere else to put the money.

**Due-this-period visibility.** A yearly outgoing whose due date falls in the active
period is called out wherever it matters, regardless of its billing mode: a warning
banner on the Overview tab lists everything due, and its row on the Accounts page is
highlighted with a "Due this period" badge. The Dashboard goes further with a **Yearly
bills** widget that gives advance notice — anything due this calendar month or within
the next three, labelled "Due this month" / "Due in 1 month" / etc., soonest first —
so a bill can't sneak up on you even outside the active budget period.

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

**Money to move.** Because a split or surplus amount recomputes every period, it isn't a
number you can memorise — it has to be read off the app each time you update a standing
order. The bottom of the Overview tab (and the Dashboard, see below) shows a **Money to
move** block: every transfer for the active period, grouped by source account, with its
next payment day. Each row stays to one line — the destination account, the amount, and
the day — with a small ⓘ next to split/surplus transfers; hover or focus it for the
plain-language derivation (e.g. "share of Joint's £2,420 shortfall, weighted by
disposable income") without it cluttering the row. Each row has an edit/delete pencil,
but a *new* transfer is added from the Accounts page.

## One-off outgoings

Future-dated single payments (a car service due in November, a repair you know is
coming) that only show up in the budget period they actually fall in — they don't
clutter every period like a recurring outgoing would. A one-off can optionally be linked
to a pot, so you can save toward it in advance; once linked, the Accounts page shows a
covered/uncovered badge comparing the pot's saved balance against the payment amount.
For something that recurs every year (an annual insurance renewal), a **yearly
outgoing** with "due period only" billing (see above) is usually the better fit — it
survives into next year automatically instead of needing to be recreated by hand.

## Overview: the budget summary

The Overview tab totals income vs. outgoings (and transfers) for the selected period —
across all accounts, or per-account — and shows the **surplus**: what's left after
everything recurring is accounted for, then an **adjusted surplus** that also factors in
this period's one-off payments. Unallocated surplus is called out deliberately, as a
nudge toward putting it in a pot — the app never allocates it for you.

## Pots

Pots are savings goals: a name, a target amount, a target date, and a monthly
contribution target. Each period, you log what you actually saved into a pot —
resubmitting a logged amount for the same period corrects it rather than creating a
duplicate. From that, the app tracks status:

- **Ahead** — you've saved more than expected to date.
- **On track** — saved matches expected.
- **Behind** — saved is short of expected; the app shows the new per-remaining-period
  amount needed to still hit the target by its deadline, with a one-click **"Set monthly
  target to £X"** button if you want to accept the adjustment. Ignoring the nudge needs
  no action — it's a suggestion, never enforced.

A pot can optionally link to a **Project**, a **one-off outgoing**, or a **yearly
outgoing** (see above) — the same covered/uncovered badge appears wherever the linked
bill is shown. Pot coverage is advisory only: it never deducts from the budget, so
there's no double-counting between "money saved in the pot" and "bill due".

Click a pot's name to open its detail page, which is where its full contribution
history lives — every period you've logged an actual amount for, not just the current
one.

## Timeline

A visual timeline of every dated "stop" (income, outgoing, transfer) in the current month,
one small chart per account with its running balance — useful for seeing at a glance *when*
money moves, not just the totals. Same-day entries in one account collapse into a single
marker badged with a count; click or tab to a marker to list that day's entries and
resulting balance directly below that account's chart.

## Flow

A Sankey-style diagram of where money moves between accounts for the period — income in,
outgoings out, transfers between accounts — as a single picture rather than a table. With
a realistic number of outgoings, one node per bill gets busy fast — tick **Group bills by
category** to collapse each account's bills into one node per category instead (one-offs
bucket into a shared "One-offs" node), then untick it to drill back into individual bills.
