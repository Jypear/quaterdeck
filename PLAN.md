# Quaterdeck — Project Plan

## Overview

Quaterdeck is a self-hosted, open-source personal budgeting and productivity platform. Users track multiple income streams across multiple accounts, manage outgoings, monitor inter-account transfers, and allocate surplus into pots — all within a configurable budget window. Tasks, calendar, and projects tie the financial picture together with planning.

---

## Core Purpose

- Personal budget planning: income vs. outgoings, surplus allocation
- Multi-account flow tracking including inter-account transfers
- Link surplus to pots and projects; plan future large expenses
- Unified workspace: budget, tasks, calendar, projects, notes
- Lightweight AI-assisted notes as a bonus feature

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend framework | Django |
| API | Django REST Framework (DRF) |
| Frontend | Django templates + HTMX + Alpine.js |
| CSS | Bootstrap 5 (mobile-first) |
| Database | PostgreSQL |
| Package manager | uv |
| Linter / formatter | Ruff |
| Containerization | Docker / Docker Compose |
| AI integration | Provider-agnostic, optional bonus feature |

---

## Architecture Decisions

### Frontend
Django server-rendered templates with HTMX for dynamic interactions and Alpine.js for lightweight client-side state. Bootstrap 5, **mobile-first** from day one with full desktop support.

### Database
PostgreSQL.

### Auth & Access Control
- Single primary user model per instance — all data belongs to the instance
- Optional password protection via `REQUIRE_LOGIN` setting
- When enabled, gates the entire app behind Django session auth
- When disabled, open access (suitable for private home network / VPN deployment)
- Collaboration: share access by sharing credentials or disabling the gate

### Currency
Single currency configured at the instance level in Settings. No per-entry multi-currency.

### AI Provider
Optional, provider-agnostic. Users configure provider + API key in settings if they want the notes AI feature. Initial providers:
- Anthropic (Claude)
- OpenAI
- Ollama (local, for fully air-gapped self-hosting)

---

## Features

### Budget

The core of the app. Budgeting operates in one of three view modes: **weekly**, **monthly**, or **yearly**. All recurring entries are normalised to the active view period for totals.

#### Budget Window
- User-defined period start date (e.g. 28th of the month = payday to payday)
- The active period always runs from the configured start date forward one week / month / year
- Switching view modes re-normalises the same entries — no separate budget per mode

#### Accounts
- [x] User defines named accounts (e.g. "Personal Current", "Joint Account", "Savings")
- [x] Each income stream and outgoing is assigned to an account
- [x] Inter-account transfers are first-class entries (e.g. "Transfer £X from Personal to Joint on the 1st")
- [x] Each outgoing is linked to the account it comes out of — transfers are checked to ensure the receiving account is sufficiently funded to cover its outgoings
- [x] Per-account view: income in, outgoings out, transfers in/out, and whether the account is covered for the period
- [x] Accounts are independently selectable for display — user can view one account, several, or all together
- [x] No grouping or percentage-based splitting — account selection and manual transfer amounts give the user full control

#### Income
- [x] Multiple named income streams per account (e.g. salary, dividends, freelance, partner's salary)
- [x] Each stream: name, amount, account, frequency (weekly / monthly / yearly)
- [x] Normalised to active view period for totals

#### Outgoings
- [x] Categorised recurring expenses per account (e.g. rent, subscriptions, groceries)
- [x] Each outgoing: name, amount, category, account, frequency
- [x] **Actual vs. budgeted**: user can log the real amount spent against a recurring outgoing for the current period — inline HTML form on the accounts page posts to `log_variance`, using `update_or_create` on the period so resubmitting corrects it instead of erroring
- [x] Variance (actual − budgeted) flows back into the surplus calculation, affecting pot contributions for that period

#### One-off Outgoings
- [x] Future-dated single payments (e.g. a large bill due in November)
- [x] Visible only in the budget period they fall in
- [x] Can be flagged to create or top up a linked pot — allowing the user to save toward it monthly ahead of time
- [ ] Pot-linked one-offs show a "covered / uncovered" status based on pot balance vs. payment amount — not built yet

#### Budget Summary
- [x] Total income vs. total outgoings for the selected period (across all accounts)
- [x] Per-account breakdown available
- [x] Surplus after all recurring outgoings and transfers
- [x] Adjusted surplus after actual spend variances
- [x] Visual breakdown (Bootstrap progress bars / simple chart)
- [x] Unallocated surplus prominently shown as a nudge to allocate to pots

#### Pots
- [x] Named pots with a target amount, target date, and a monthly contribution target
- [x] Each period the user confirms the actual amount saved into the pot (manual entry) — inline HTML form on the pots page posts to `log_pot_entry`, same overwrite-on-resubmit pattern as outgoing variances
- [x] App compares actual vs. monthly target: on track / behind / ahead
- [x] Shows how much more is needed per remaining period to hit the target by the deadline
- [x] User can be prompted: "You're behind — adjust your monthly contribution to £X to still hit the target"
- [ ] User confirms whether to accept the adjusted contribution or leave it as-is — still deferred, see below
- [x] App shows unallocated surplus as guidance — never forces allocation
- [x] Spend variances in a period reduce the available surplus to contribute
- [x] Pots can be linked to a one-off outgoing or a Project

### Tasks
- [x] To-do list: title, due date, priority, status
- [x] Tasks linkable to projects and calendar events
- [x] Large upcoming payments can be added as tasks with a budget amount, visible on calendar

### Calendar
- [x] Calendar view surfacing tasks and scheduled events
- [ ] Recurring outgoings and income dates visible — deferred, no per-entry date field (only `frequency`) to plot individually; budget period-start is shown as a stand-in marker
- [x] One-off outgoing due dates shown
- [x] Pot target dates shown

### Projects
- [x] Create and manage projects
- [x] A project is a container: links tasks, notes, pots, and calendar events
- [ ] Project budget view: shows linked pot(s), total allocated, and progress toward project cost — not built yet

### Notes
- [x] Free-form note taking per project or standalone
- [x] Optional AI enrichment: when AI is configured, the notes page interprets typed notes and suggests actions (create a linked task, link to a project)
- [x] AI interaction is on-demand only — never automatic

### API & Webhooks
- [x] RESTful API via DRF for all core resources — 12 `ModelViewSet`s under `/api/` (`api/urls.py`), one per budget/notes/projects/tasks model, session-authenticated
- [x] Inbound webhook endpoints for external events — `POST /webhooks/inbound/`, HMAC-signed against `Settings.webhook_inbound_secret`, routes on a `type` field (ships `create_task`)
- [x] Outbound webhook support for triggering external automations — `WebhookEndpoint` subscriptions fire signed POSTs on `task`/`pot`/`note`/`oneoff` events (`webhooks/signals.py`, `webhooks/services.py`), delivery logged to `WebhookDelivery`

### Settings
- [x] `REQUIRE_LOGIN` toggle for optional password protection
- [x] Currency selection (instance-wide)
- [x] Budget window: view mode (weekly / monthly / yearly) + period start date
- [x] AI provider configuration (provider, API key, model)
- [x] Webhook signing secrets management — inbound secret shown + regenerable on the Settings page; per-endpoint outbound secrets managed on the Webhooks page

---

## Deployment

- Docker image for the application server
- Docker Compose for local and self-hosted deployment (app + PostgreSQL + optional reverse proxy)
- Environment-based configuration (`.env` file)
- Migrations and setup via Django management commands
- Bootstrap 5 served locally (no CDN dependency)

---

## Deferred / Future Decisions

- **Pot adjustment UX**: Passive suggestion displayed inline on the pot card — user can tap to accept the recalculated monthly contribution or ignore it. Revisit when building the pots UI.

---

## Data Models

### Settings
| Field | Type | Notes |
|---|---|---|
| currency | CharField | e.g. GBP, USD — instance-wide |
| budget_mode | CharField | weekly / monthly / yearly |
| budget_start_day | IntegerField | Day of week (1–7) or day of month (1–31) |
| require_login | BooleanField | Gates app behind session auth when true |
| ai_provider | CharField | anthropic / openai / ollama / none |
| ai_api_key | CharField | Encrypted, nullable |
| ai_model | CharField | e.g. claude-sonnet-4-6 |

### Account
| Field | Type | Notes |
|---|---|---|
| name | CharField | e.g. "Personal Current", "Joint" |
| account_type | CharField | personal / joint / savings / other |
| is_active | BooleanField | Soft-disable without deleting |

### IncomeStream
| Field | Type | Notes |
|---|---|---|
| name | CharField | e.g. "Salary", "Dividends" |
| amount | DecimalField | |
| frequency | CharField | weekly / monthly / yearly |
| account | FK → Account | Account this income lands in |

### Transfer
| Field | Type | Notes |
|---|---|---|
| name | CharField | e.g. "Joint account contribution" |
| from_account | FK → Account | |
| to_account | FK → Account | |
| amount | DecimalField | |
| frequency | CharField | weekly / monthly / yearly |

### OutgoingCategory
| Field | Type | Notes |
|---|---|---|
| name | CharField | User-defined, e.g. "Groceries", "Rent" |

### Outgoing
| Field | Type | Notes |
|---|---|---|
| name | CharField | e.g. "Netflix", "Council Tax" |
| amount | DecimalField | Budgeted amount |
| category | FK → OutgoingCategory | |
| frequency | CharField | weekly / monthly / yearly |
| account | FK → Account | Account this comes out of |

### OutgoingVariance
| Field | Type | Notes |
|---|---|---|
| outgoing | FK → Outgoing | |
| period_start | DateField | Start of the period this variance belongs to |
| actual_amount | DecimalField | What was actually spent |
| delta | DecimalField | Computed: actual − budgeted (positive = overspent) |

### OneOffOutgoing
| Field | Type | Notes |
|---|---|---|
| name | CharField | e.g. "Car service" |
| amount | DecimalField | |
| due_date | DateField | Determines which period it appears in |
| account | FK → Account | |
| linked_pot | FK → Pot, nullable | Pot being saved toward this payment |

### Pot
| Field | Type | Notes |
|---|---|---|
| name | CharField | e.g. "Holiday 2026" |
| target_amount | DecimalField | |
| target_date | DateField | Deadline to reach the target |
| monthly_target | DecimalField | Suggested contribution per period |
| linked_project | FK → Project, nullable | |
| linked_one_off | FK → OneOffOutgoing, nullable | |

### PotEntry
| Field | Type | Notes |
|---|---|---|
| pot | FK → Pot | |
| period_start | DateField | Start of the period this entry belongs to |
| actual_amount | DecimalField | What the user actually saved this period |

### Project
| Field | Type | Notes |
|---|---|---|
| name | CharField | |
| description | TextField | |
| budget | DecimalField | Total cost of the project, nullable |

### Task
| Field | Type | Notes |
|---|---|---|
| title | CharField | |
| due_date | DateField, nullable | |
| priority | CharField | low / medium / high |
| status | CharField | todo / in_progress / done |
| linked_project | FK → Project, nullable | |
| budget_amount | DecimalField, nullable | For tasks representing a future payment |

### Note
| Field | Type | Notes |
|---|---|---|
| title | CharField | |
| body | TextField | |
| linked_project | FK → Project, nullable | |
| created_at | DateTimeField | |
| updated_at | DateTimeField | |

---

## Next Steps

1. [x] Set up the Django project scaffold (uv + Ruff + Docker)
2. [x] Implement data models and migrations
3. [x] Define the DRF API contract (resources, endpoints, auth scheme)
4. [x] Build core budget views (account summary, income/outgoings, surplus) — budget engine (`budget/services.py`) plus overview/accounts/pots pages, with HTMX-driven view-mode and account switching. Full HTML CRUD for accounts/income/outgoings, plus inline per-period logging for outgoing variances and pot entries (`budget/forms.py`, `log_variance`, `log_pot_entry`) — closes the feedback loop the engine already computed. Full HTML CRUD added for Transfers, One-off Outgoings, Outgoing Categories, and Pot creation/edit/delete (this pass) — the budget feature is now usable end-to-end without touching Django admin
5. [x] Build pots, projects, tasks, calendar
   - [x] Pots — progress tracking, on-track/behind/ahead status, and per-period saved-amount logging
   - [x] Projects, Tasks — full HTML CRUD (create/edit/delete), matching the budget app's pattern
   - [x] Calendar — month grid aggregating task due dates, one-off due dates, pot target dates, and budget period markers (`core/views.py::CalendarView`)
6. [x] Notes page — full HTML CRUD, plus on-demand AI enrichment: an "Enrich" button sends the note to the configured provider and returns clickable suggested actions (create a linked task, link to a project)
7. [x] AI provider abstraction layer — `ai/providers.py` (Anthropic/OpenAI/Ollama) is now called from `notes/views.py::enrich_note`; `anthropic`/`openai` added as dependencies. `ai` app still isn't in `INSTALLED_APPS` — it has no models/migrations, so it doesn't need to be; imported as a plain module.
   - A user-facing Settings page now exists (`core:settings`) to configure `ai_provider` / `ai_api_key` / `ai_model` (previously admin-only)

8. [x] Webhooks — new `webhooks` app: outbound `WebhookEndpoint` subscriptions (HMAC-signed delivery via `webhooks/services.py`, fired from `webhooks/signals.py` on task/pot/note/one-off changes) plus an inbound `POST /webhooks/inbound/` receiver authenticated by a Settings-stored HMAC secret. Both endpoint CRUD and the delivery log get HTML pages (`templates/webhooks/`); `WebhookEndpoint`/`WebhookDelivery` also registered on the DRF API.

**Still missing:** Project budget view (linked pot progress vs. project cost), recurring income/outgoings/transfers on the calendar (no per-entry date field).
