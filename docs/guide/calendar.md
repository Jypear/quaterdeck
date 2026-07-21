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
create or edit it (day-of-month for monthly/yearly, day-of-week for weekly) — there's
also an optional weekend adjustment, and for fortnightly-or-longer weekly schedules, an
interval + anchor date. Leave the day blank and the entry still budgets correctly — it
simply won't appear on the calendar, and the period-start marker stands in for it instead.
