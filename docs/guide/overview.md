# Overview

Quaterdeck is a single-instance, self-hosted workspace for your household finances and
the tasks/projects around them. There's no per-user data isolation — everything belongs
to the instance, and access is either open (private network) or gated behind one shared
login, per [`REQUIRE_LOGIN`](settings.md).

## The nav

Six sections plus Settings:

| Section | What it's for |
|---|---|
| **Dashboard** | Landing page: this period's surplus at a glance, plus what's coming up in the next two weeks. |
| **[Budget](budget.md)** | Accounts, income, outgoings, transfers, pots, and two visualisations (Timeline, Flow). The core of the app. |
| **[Tasks](tasks.md)** | A to-do list, optionally linked to projects or a future payment. |
| **[Calendar](calendar.md)** | Everything with a date — tasks, one-off payments, pot deadlines, and scheduled recurring entries — on one month grid. |
| **[Projects](projects.md)** | Containers that tie tasks, notes, and pots together, with their own budget-progress view. |
| **[Notes](notes.md)** | Free-form notes, with optional on-demand AI help. |
| **[Settings](settings.md)** | Currency, budget window, login gate, AI provider, webhooks. |

## The budget window

Almost everything on the Dashboard and in Budget is computed relative to one **active
period** — a window that runs forward from a configured start day (Settings → Budget
window), in **weekly**, **monthly**, or **yearly** chunks. Every income stream, outgoing,
and transfer has its own `frequency`, and the budget engine normalises all of them into
that one active period so totals are always comparable, whatever their real-world cadence.

Switching the view mode (weekly/monthly/yearly) re-normalises the *same* underlying
entries — it's a different lens on one budget, not a separate one per mode.

## Where to go next

Start with [Budget & pots](budget.md) — it's where most of the day-to-day setup and
upkeep happens. Everything else (Calendar, Projects, the AI features in Notes) mostly
reads from data you enter there.
