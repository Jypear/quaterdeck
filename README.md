<p align="center">
  <img src="static/img/favicon.svg" alt="Quaterdeck logo" width="64" height="64">
</p>

<h1 align="center">Quaterdeck</h1>
<p align="center">Self-hosted personal life OS. Budget, plan, and manage projects from one place — with an AI-powered notes layer. Built with Django.</p>

## Features

- **Budget** — multi-account income, outgoings, and transfers, normalised across weekly / monthly / yearly views
- **Tasks & Projects** — projects link tasks, notes, pots, and calendar events together
- **Calendar** — dated items from budget, tasks, and projects on one timeline
- **Notes** — with optional, on-demand AI enrichment (Claude, OpenAI, or a local Ollama model)

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

## Quick start

Run the pre-built image (published to `ghcr.io/jypear/quaterdeck` on every release —
no clone or build needed):

```bash
curl -O https://raw.githubusercontent.com/Jypear/quaterdeck/main/docker-compose.prod.yml
curl -O https://raw.githubusercontent.com/Jypear/quaterdeck/main/.env.example
cp .env.example .env
# edit .env and set SECRET_KEY (see the comment above it for how to generate one)
docker compose -f docker-compose.prod.yml up -d
```

The app is then available at http://localhost:8000. On first boot, create an admin user:

```bash
docker compose -f docker-compose.prod.yml exec web uv run python manage.py createsuperuser
```

See [Deployment](https://jypear.github.io/quaterdeck/guides/deployment/) for image tags
and pinning a specific version.

### Building from source

```bash
git clone https://github.com/Jypear/quaterdeck.git && cd quaterdeck
cp .env.example .env
docker compose up --build
```

### Local development (no Docker)

Requires Python 3.12+, PostgreSQL, and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

## Documentation

Full guides and API reference: **https://jypear.github.io/quaterdeck/**

Docs source lives in [`docs/`](docs/) and is built with MkDocs; it publishes
automatically on every merge to `main`.

## License

See [LICENSE](LICENSE).
