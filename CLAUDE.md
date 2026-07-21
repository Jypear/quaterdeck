# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working With Claude

- **Never run `git commit` or `git push`** — the user handles all commits. You may run read-only git commands (`git status`, `git log`, `git diff`) freely.
- **After every response where you made code changes**, include a `---` separator followed by a **Commit message breakdown** section: a short imperative subject line, then a bullet list of what changed and why. Keep it concise so the user can copy it directly into a commit message.

## Project Overview

Quaterdeck is a self-hosted personal life OS — budget tracking, task management, projects, calendar, and AI-assisted notes — built as a Django monolith with a server-rendered frontend. See `PLAN.md` for the full feature spec and data models.

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Django + Django REST Framework |
| Frontend | Django templates + HTMX + Alpine.js |
| CSS | Bootstrap 5 (mobile-first, no CDN) |
| Database | PostgreSQL |
| Package manager | uv |
| Linter / formatter | Ruff |
| Containerization | Docker / Docker Compose |

## Commands

Once the project scaffold exists:

```bash
# Install dependencies
uv sync

# Run dev server
uv run python manage.py runserver

# Run migrations
uv run python manage.py migrate

# Run tests
uv run python manage.py test

# Run a single test
uv run python manage.py test app.tests.TestClassName.test_method

# Lint and format
uv run ruff check .
uv run ruff format .

# Docs: live preview / strict build check
uv run mkdocs serve
uv run mkdocs build --strict
```

## Architecture

### Frontend approach
Server-rendered Django templates. HTMX handles dynamic partial page updates (form submissions, list refreshes, etc.) without a full SPA. Alpine.js handles lightweight client-side state only — use it sparingly for things HTMX can't handle (e.g. open/close toggles, local UI state). Bootstrap 5, mobile-first from day one.

### Auth model
Single-user per instance. `REQUIRE_LOGIN` setting (stored in the Settings model) gates the entire app behind Django session auth when `True`. When `False`, the app is open (for private network/VPN deployments). No per-user data isolation — all data belongs to the instance.

### Budget normalisation
All income, outgoing, and transfer amounts have a `frequency` field (`weekly` / `monthly` / `yearly`). The budget engine normalises all entries to the active view period for totals. The active period runs forward from the user-configured `budget_start_day`. Switching view modes re-normalises the same underlying entries — there are no separate budgets per mode.

### Currency
Instance-wide single currency configured in Settings. No per-entry multi-currency.

### AI integration
Optional, provider-agnostic. Configured in Settings (`ai_provider`, `ai_api_key`, `ai_model`). Providers: Anthropic (Claude), OpenAI, Ollama. AI is on-demand only — never triggered automatically. Abstracted behind a provider interface so the frontend doesn't know which backend is in use.

### API
DRF REST API for all core resources. Inbound and outbound webhook support.

## Key Domain Concepts

- **Accounts**: Named bank accounts (personal / joint / savings / other). Income, outgoings, and transfers are all assigned to accounts.
- **Transfers**: First-class entries — not outgoings. Modelled separately with `from_account` / `to_account`.
- **Pots**: Savings goals with a target amount and date. Linked optionally to a Project or OneOffOutgoing. Per-period contributions tracked via `PotEntry`.
- **OutgoingVariance**: Records actual vs. budgeted spend for a given period. Deltas flow back into the surplus calculation.
- **OneOffOutgoing**: Future-dated single payments. Appear only in the budget period they fall in. Can be pot-linked.
- **Projects**: Containers that link tasks, notes, pots, and calendar events together.

## Development Notes

- Use `uv` for all Python package management — not pip directly.
- Ruff is the single tool for both linting and formatting; run both checks before committing.
- Bootstrap 5 must be served locally — no CDN links.
- All financial amounts use `DecimalField` — never `FloatField`.
- `ai_api_key` in Settings must be stored encrypted.

## Documentation

Docs are Markdown in `docs/`, built by MkDocs (config in `mkdocs.yml`, deps in the `docs`
dependency group) and published to GitHub Pages by `.github/workflows/docs.yml` on every
merge to `main` — live at https://jypear.github.io/quaterdeck/.

- The **API reference** pages (`docs/reference/*.md`) are generated from module/class
  docstrings via mkdocstrings — keep docstrings in `models.py`/`services.py`/etc.
  accurate, since that's the primary source for those pages.
- When a change adds or alters a user-facing feature, or changes something covered in
  `docs/guides/`, update the relevant guide in the same change.
- Preview locally with `uv run mkdocs serve`; `uv run mkdocs build --strict` is the same
  check CI runs (fails on broken links/refs).
