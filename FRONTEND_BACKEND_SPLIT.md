# Frontend / Backend Split

## Current ownership

The project is now organized as a split frontend/backend setup:

- `frontend/`
  - Next.js frontend
  - Owns all user-facing pages:
    - public storefront
    - buyer center
    - seller center
    - staff/admin pages
- `myapp/api/`
  - Django REST Framework API
  - Owns JSON responses, permissions, validation, and backend actions
- `myapp/services/`
  - Business logic
- `myapp/repositories/`
  - JSON-backed persistence

## What changed

- Old Django template routes such as:
  - `/products/`
  - `/cart/`
  - `/orders/`
  - `/me/...`
  - `/staff/...`
- are no longer rendered by Django templates.
- They now redirect to the matching Next.js routes.

## Django template status

The `templates/` directory is no longer the main frontend.
It now remains only for backend-owned pages such as:

- API route record
- HTML write migration record
- no-db infrastructure document

## Routing responsibility

### Next.js

Owns page rendering for:

- `/`
- `/products`
- `/products/[slug]`
- `/products/compare`
- `/brands/[brand_slug]`
- `/categories/[category_slug]`
- `/community`
- `/community/[id]`
- `/login`
- `/register`
- `/cart`
- `/checkout`
- `/orders`
- `/orders/[id]`
- `/me/...`
- `/staff/...`

### Django

Owns:

- `/api/v1/...`
- `/admin/`
- `/docs/...`
- `/health/...`
- CSV export endpoints

## Important note

There are still legacy `/api/...` alias routes in Django for backward compatibility.
They do not represent a second frontend. They are only compatibility API aliases.
