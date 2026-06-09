# Local Setup

## Current expectation

- Local development runs against Django ORM and a configured database.
- `data/*.json` is no longer part of the active storage path.

## Basic steps

1. Create and activate the virtual environment.
2. Install Python dependencies.
3. Configure `store/.env` with local database settings.
4. Run `manage.py migrate`.
5. Start Django with `..\Scripts\python.exe manage.py runserver`.

## Notes

- Keep `store/.env`, local dumps, and exported data out of Git.
- If a document or comment still mentions JSON persistence, treat it as legacy migration context.
