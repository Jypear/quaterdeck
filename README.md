# quaterdeck
Self-hosted personal life OS. Budget, plan, and manage projects from one place — with an AI-powered notes layer. Built with Django.

## Run it

```bash
cp .env.example .env
# edit .env and set SECRET_KEY (see the comment above it for how to generate one)
docker compose up --build
```

The app is then available at http://localhost:8000. On first boot, create an admin user:

```bash
docker compose exec web uv run python manage.py createsuperuser
```
