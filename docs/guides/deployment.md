# Deployment

Quaterdeck ships as a Django app behind Gunicorn + Whitenoise, backed by PostgreSQL, and
is intended to run via Docker Compose on a home server / private network.

## Environment variables

Copy `.env.example` to `.env` and set at minimum:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Required — the app won't start without it. Generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"`. |
| `DEBUG` | `True` for local dev, `False` in production. |
| `ALLOWED_HOSTS` | Comma-separated hostnames the app will serve. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection. |

`ai_api_key` (configured in the Settings model via the UI, not `.env`) is stored
encrypted — see `core.fields`.

## Docker Compose

`docker-compose.yml` defines two services:

- **db** — `postgres:16-alpine`, with a healthcheck the `web` service waits on.
- **web** — built from the repo `Dockerfile`, served on port 8000.

```bash
cp .env.example .env
docker compose up --build
docker compose exec web uv run python manage.py createsuperuser
```

## Running without Docker

See [Getting started](getting-started.md#local-development-no-docker) for the bare
`uv run` workflow against a local PostgreSQL instance.
