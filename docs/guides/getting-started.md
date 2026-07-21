# Getting started

## Quickest path: Docker

```bash
cp .env.example .env
# edit .env and set SECRET_KEY (see the comment above it for how to generate one)
docker compose up --build
```

The app is then available at <http://localhost:8000>. On first boot, create an admin
user:

```bash
docker compose exec web uv run python manage.py createsuperuser
```

## Local development (no Docker)

Requires Python 3.12+, PostgreSQL, and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

Other common commands:

```bash
# Run tests
uv run python manage.py test

# Run a single test
uv run python manage.py test app.tests.TestClassName.test_method

# Lint and format
uv run ruff check .
uv run ruff format .
```

## Building the docs

```bash
uv sync --group docs
uv run mkdocs serve      # live preview at http://127.0.0.1:8000
uv run mkdocs build --strict   # verify — fails on broken links/references
```
