FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# Copy project source
COPY . .

# Collect static files. Uses a build-time-only placeholder SECRET_KEY — collectstatic
# doesn't touch the DB or need the real secret; runtime secrets come from the container's
# env_file instead, so .env never needs to be baked into the image.
RUN SECRET_KEY=build-time-placeholder uv run python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "-c", "uv run python manage.py migrate --noinput && uv run gunicorn quaterdeck.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 90"]
