# Calendar

A month grid pulling together everything with a date, from across the app:

- Task due dates
- One-off outgoing due dates
- Pot target dates
- Recurring income, outgoings, and transfers — **if** they've been given a scheduled pay
  date
- A "Budget period" marker on each period's start date

## Scheduling recurring entries

Income, outgoings, and transfers only have a `frequency` (weekly/monthly/yearly) by
default — that's enough to compute budget totals, but not enough to place them on a
specific day. To have one show up on the calendar, give it a **recurring day** when you
create or edit it (day-of-month for monthly, day-of-week for weekly) — there's also an
optional weekend adjustment, and for fortnightly-or-longer weekly schedules, an interval
+ anchor date. Leave the day blank and the entry still budgets correctly — it simply
won't appear on the calendar, and the period-start marker stands in for it instead.

Yearly entries need one more field: a **recurring month**, alongside the recurring day,
to say which day of which month it falls on (e.g. day 27, month 3 for 27 March). Without
a month, a yearly entry still budgets correctly but can't be placed on the calendar —
same as leaving the day blank.
