"""Session-backed personalization helpers.

This module stores favorites, recently viewed products, and compare lists in
the Django session. Personalization is scoped by the currently logged-in demo
user so different accounts sharing one browser do not see each other's data.
"""

from __future__ import annotations

from typing import Dict, List

from ..repositories import local_store

FAVORITES_KEY = "favorite_products"
RECENT_VIEWS_KEY = "recent_products"
COMPARE_PRODUCTS_KEY = "compare_products"
SESSION_USER_KEY = "demo_user"
GUEST_BUCKET_KEY = "__guest__"
MAX_RECENT_VIEWS = 8
MAX_COMPARE_PRODUCTS = 4


def _session_bucket_name(session) -> str:
    user = session.get(SESSION_USER_KEY)
    if isinstance(user, dict):
        username = str(user.get("username", "")).strip().lower()
        if username:
            return username
    return GUEST_BUCKET_KEY


def _ensure_bucket(session, key: str) -> List[str]:
    bucket_name = _session_bucket_name(session)
    raw = session.get(key)

    if isinstance(raw, list):
        # Legacy sessions stored one shared list. Keep it under the guest bucket
        # instead of attaching it to whichever user logs in next.
        raw = {GUEST_BUCKET_KEY: list(raw)}
        session[key] = raw
        session.modified = True
    elif not isinstance(raw, dict):
        raw = {}
        session[key] = raw
        session.modified = True

    bucket = raw.get(bucket_name)
    if not isinstance(bucket, list):
        bucket = []
        raw[bucket_name] = bucket
        session[key] = raw
        session.modified = True

    return bucket


def _replace_bucket(session, key: str, values: List[str]) -> None:
    bucket_name = _session_bucket_name(session)
    raw = session.get(key)

    if isinstance(raw, list):
        raw = {GUEST_BUCKET_KEY: list(raw)}
    elif not isinstance(raw, dict):
        raw = {}

    raw[bucket_name] = values
    session[key] = raw
    session.modified = True


def clear_guest_buckets(session) -> None:
    for key in (FAVORITES_KEY, RECENT_VIEWS_KEY, COMPARE_PRODUCTS_KEY):
        raw = session.get(key)
        if isinstance(raw, list):
            raw = {GUEST_BUCKET_KEY: []}
        elif isinstance(raw, dict):
            raw = dict(raw)
            raw[GUEST_BUCKET_KEY] = []
        else:
            raw = {GUEST_BUCKET_KEY: []}
        session[key] = raw
    session.modified = True


def _merge_slug_lists(primary: List[str], secondary: List[str], *, max_items: int | None = None) -> List[str]:
    merged: List[str] = []
    for slug in [*primary, *secondary]:
        if slug and slug not in merged:
            merged.append(slug)
    if max_items is not None:
        return merged[:max_items]
    return merged


def migrate_guest_buckets(session, username: str) -> None:
    bucket_name = username.strip().lower()
    if not bucket_name:
        return

    for key, max_items in (
        (FAVORITES_KEY, None),
        (RECENT_VIEWS_KEY, MAX_RECENT_VIEWS),
        (COMPARE_PRODUCTS_KEY, MAX_COMPARE_PRODUCTS),
    ):
        raw = session.get(key)
        if isinstance(raw, list):
            raw = {GUEST_BUCKET_KEY: list(raw)}
        elif not isinstance(raw, dict):
            raw = {}
        else:
            raw = dict(raw)

        guest_values = raw.get(GUEST_BUCKET_KEY)
        target_values = raw.get(bucket_name)
        guest_values = list(guest_values) if isinstance(guest_values, list) else []
        target_values = list(target_values) if isinstance(target_values, list) else []

        raw[bucket_name] = _merge_slug_lists(guest_values, target_values, max_items=max_items)
        raw[GUEST_BUCKET_KEY] = []
        session[key] = raw

    session.modified = True


def get_favorite_slugs(session) -> List[str]:
    return list(_ensure_bucket(session, FAVORITES_KEY))


def is_favorite(session, slug: str) -> bool:
    return slug in get_favorite_slugs(session)


def toggle_favorite(session, product: Dict[str, object]) -> bool:
    slugs = get_favorite_slugs(session)
    slug = str(product["slug"])
    if slug in slugs:
        slugs.remove(slug)
        active = False
    else:
        slugs.insert(0, slug)
        active = True
    _replace_bucket(session, FAVORITES_KEY, slugs)
    return active


def get_favorite_products(session) -> List[Dict[str, object]]:
    products = []
    for slug in get_favorite_slugs(session):
        product = local_store.get_product_by_slug(slug)
        if product:
            products.append(product)
    return products


def record_recent_view(session, product: Dict[str, object]) -> None:
    slugs = list(_ensure_bucket(session, RECENT_VIEWS_KEY))
    slug = str(product["slug"])
    if slug in slugs:
        slugs.remove(slug)
    slugs.insert(0, slug)
    _replace_bucket(session, RECENT_VIEWS_KEY, slugs[:MAX_RECENT_VIEWS])


def get_recent_products(session) -> List[Dict[str, object]]:
    products = []
    for slug in _ensure_bucket(session, RECENT_VIEWS_KEY):
        product = local_store.get_product_by_slug(slug)
        if product:
            products.append(product)
    return products


def get_compare_slugs(session) -> List[str]:
    return list(_ensure_bucket(session, COMPARE_PRODUCTS_KEY))


def is_in_compare(session, slug: str) -> bool:
    return slug in get_compare_slugs(session)


def toggle_compare(session, product: Dict[str, object]) -> tuple[bool, str]:
    slugs = get_compare_slugs(session)
    slug = str(product["slug"])
    removed_slug = ""
    if slug in slugs:
        slugs.remove(slug)
        active = False
    else:
        slugs.insert(0, slug)
        active = True
        if len(slugs) > MAX_COMPARE_PRODUCTS:
            removed_slug = str(slugs.pop())
    _replace_bucket(session, COMPARE_PRODUCTS_KEY, slugs)
    return active, removed_slug


def get_compare_products(session) -> List[Dict[str, object]]:
    products = []
    for slug in get_compare_slugs(session):
        product = local_store.get_product_by_slug(slug)
        if product:
            products.append(product)
    return products
