# Architecture

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Django + Django REST Framework |
| Frontend | Django templates + HTMX + Alpine.js |
| CSS | Bootstrap 5 (mobile-first, no CDN) |
| Database | PostgreSQL |
| Package manager | uv |
| Linter / formatter | Ruff |
| Containerization | Docker / Docker Compose |

## Frontend approach

Server-rendered Django templates. HTMX handles dynamic partial page updates (form
submissions, list refreshes) without a full SPA. Alpine.js handles lightweight
client-side state only — used sparingly for things HTMX can't do (open/close toggles,
local UI state). Bootstrap 5, mobile-first from day one.

## Auth model

Single-user per instance. The `REQUIRE_LOGIN` setting (stored in the `Settings` model)
gates the entire app behind Django session auth when `True`. When `False`, the app is
open — intended for private network / VPN deployments. There is no per-user data
isolation: all data belongs to the instance.

## Currency

Instance-wide single currency, configured in Settings. No per-entry multi-currency.

## Budget normalisation

Every income, outgoing, and transfer has a `frequency` field (`weekly` / `monthly` /
`yearly`). The budget engine (`budget.services` — see [API reference](../reference/budget.md))
normalises entries to the active view period for totals. The active period runs forward
from the configured `budget_start_day`. Switching view modes re-normalises the same
underlying entries — there are no separate budgets per mode.

## AI integration

Optional, provider-agnostic, configured in Settings (`ai_provider`, `ai_api_key`,
`ai_model`). Supported providers: Anthropic (Claude), OpenAI, Ollama. AI is on-demand
only — it is never triggered automatically. The provider interface lives in
`ai.providers` (see [API reference](../reference/ai.md)), so the frontend doesn't know
which backend is in use.

## API

DRF REST API for all core resources (`api.views`), plus inbound and outbound webhook
support (`webhooks`).

## Key domain concepts

- **Accounts** — named bank accounts (personal / joint / savings / other). Income,
  outgoings, and transfers are all assigned to an account.
- **Transfers** — first-class entries, not outgoings. Modelled separately with
  `from_account` / `to_account`.
- **Pots** — savings goals with a target amount and date. Linked optionally to a Project
  or `OneOffOutgoing`. Per-period contributions are tracked via `PotEntry`.
- **OneOffOutgoing** — future-dated single payments. Appear only in the budget period
  they fall in. Can be pot-linked.
- **Projects** — containers that link tasks, notes, pots, and calendar events together.
