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
| `CSRF_TRUSTED_ORIGINS` | Comma-separated full origins (with scheme) you'll submit forms from, e.g. `https://quaterdeck.example.com`. Required in production or you'll get "CSRF verification failed" on any POST — Django checks this, not `ALLOWED_HOSTS`. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection. |

`ai_api_key` (configured in the Settings model via the UI, not `.env`) is stored
encrypted — see `core.fields`.

## Running the published image (recommended)

Every push to `main` and every version tag publishes a multi-arch (amd64 + arm64) image
to `ghcr.io/jypear/quaterdeck` — no clone or build required. Grab `docker-compose.prod.yml`
and `.env.example` from the repo, then:

```bash
cp .env.example .env
# edit .env and set SECRET_KEY (see the comment above it for how to generate one)
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec web uv run python manage.py createsuperuser
```

Image tags:

| Tag | What it points to |
|---|---|
| `latest` | Most recent version tag (recommended for most installs) |
| `X.Y.Z` / `X.Y` | A specific release — pin this for reproducible upgrades |
| `edge` | Latest commit on `main` — may be unstable |

To pin a version, edit the `image:` line in `docker-compose.prod.yml` (e.g.
`ghcr.io/jypear/quaterdeck:0.1.0`) and re-run `docker compose -f docker-compose.prod.yml
up -d`.

## Building from source

`docker-compose.yml` defines two services:

- **db** — `postgres:16-alpine`, with a healthcheck the `web` service waits on.
- **web** — built from the repo `Dockerfile`, served on port 8000.

```bash
cp .env.example .env
docker compose up --build
docker compose exec web uv run python manage.py createsuperuser
```

Use this path if you're developing against the app rather than just running it.

## Running without Docker

See [Getting started](getting-started.md#local-development-no-docker) for the bare
`uv run` workflow against a local PostgreSQL instance.
