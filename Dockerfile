FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies (cached layer)
COPY pyproject.toml .
RUN uv sync --no-dev

# Copy project source
COPY . .

# Collect static files
RUN uv run python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["uv", "run", "gunicorn", "quaterdeck.wsgi:application", "--bind", "0.0.0.0:8000"]
