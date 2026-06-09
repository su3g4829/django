# Project Structure

This project now uses Django ORM plus MySQL as the source of truth.

## Active runtime layers

- `store/`: Django project settings, routing, WSGI, and environment wiring.
- `myapp/models.py`: canonical database schema.
- `myapp/services/`: business logic used by API views and page views.
- `myapp/api/`: API-facing views and serializers/adapters.
- `templates/`: Django-rendered pages and docs views.
- `static/`: static assets.
- `frontend/`: Next.js frontend assets and client UI work.

## Data storage

- Application data should come from ORM models backed by MySQL.
- `data/*.json` is retired and should not be used as runtime persistence.
- Database dumps, exported data, and local credentials must stay out of Git.

## Legacy note

- Older references to JSON storage or `myapp/repositories/local_store.py` belong to the migration history only.
