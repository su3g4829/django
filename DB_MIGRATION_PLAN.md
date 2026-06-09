# DB Migration Plan

## Status

This migration is effectively complete for the main application path.

- Django ORM plus MySQL is the active source of truth.
- `data/*.json` is retired from runtime use.
- `myapp/repositories/local_store.py` has been removed.

## Remaining interpretation

- Any old JSON references in code comments or older notes should be treated as historical context only.
- Follow-up cleanup should focus on comment/doc wording, not on restoring JSON persistence.
