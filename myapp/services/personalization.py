"""收藏 / 比較 / 最近瀏覽的個人化 service。

來源模組：
- `myapp.repositories.local_store`

用途：
- 管理 session 內的收藏、比較、最近瀏覽資料
- 依目前登入的 demo user 做 bucket 隔離
- 避免同一台瀏覽器切換帳號時互相看到彼此的收藏與比較清單
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


# session bucket 工具：
# - 依目前登入帳號切到對應 bucket
# - 未登入時一律使用 guest bucket
def _session_bucket_name(session) -> str:
    user = session.get(SESSION_USER_KEY)
    if isinstance(user, dict):
        username = str(user.get("username", "")).strip().lower()
        if username:
            return username
    return GUEST_BUCKET_KEY


def _ensure_bucket(session, key: str) -> List[str]:
    """確保指定個人化清單在目前 bucket 中存在。"""
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
    """用新清單覆蓋目前 bucket 內的指定個人化資料。"""
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
    """清空訪客 bucket 的收藏、最近瀏覽與比較清單。"""
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
    """合併兩份 slug 清單並去重，必要時截斷長度。"""
    merged: List[str] = []
    for slug in [*primary, *secondary]:
        if slug and slug not in merged:
            merged.append(slug)
    if max_items is not None:
        return merged[:max_items]
    return merged


def migrate_guest_buckets(session, username: str) -> None:
    """登入時把訪客 bucket 合併到指定會員 bucket。"""
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
    """讀取目前 bucket 的收藏 slug 清單。"""
    return list(_ensure_bucket(session, FAVORITES_KEY))


def is_favorite(session, slug: str) -> bool:
    """檢查指定商品是否在目前 bucket 的收藏清單中。"""
    return slug in get_favorite_slugs(session)


def toggle_favorite(session, product: Dict[str, object]) -> bool:
    """切換商品收藏狀態。"""
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
    """把收藏 slug 清單轉成實際商品資料。"""
    products = []
    for slug in get_favorite_slugs(session):
        product = local_store.get_product_by_slug(slug)
        if product:
            products.append(product)
    return products


def record_recent_view(session, product: Dict[str, object]) -> None:
    """記錄最近瀏覽商品，並維持固定長度。"""
    slugs = list(_ensure_bucket(session, RECENT_VIEWS_KEY))
    slug = str(product["slug"])
    if slug in slugs:
        slugs.remove(slug)
    slugs.insert(0, slug)
    _replace_bucket(session, RECENT_VIEWS_KEY, slugs[:MAX_RECENT_VIEWS])


def get_recent_products(session) -> List[Dict[str, object]]:
    """把最近瀏覽 slug 清單轉成實際商品資料。"""
    products = []
    for slug in _ensure_bucket(session, RECENT_VIEWS_KEY):
        product = local_store.get_product_by_slug(slug)
        if product:
            products.append(product)
    return products


def get_compare_slugs(session) -> List[str]:
    """讀取目前 bucket 的商品比較 slug 清單。"""
    return list(_ensure_bucket(session, COMPARE_PRODUCTS_KEY))


def is_in_compare(session, slug: str) -> bool:
    """檢查指定商品是否在比較清單中。"""
    return slug in get_compare_slugs(session)


def toggle_compare(session, product: Dict[str, object]) -> tuple[bool, str]:
    """切換商品比較狀態，必要時回傳被擠出的舊 slug。"""
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
    """把比較 slug 清單轉成實際商品資料。"""
    products = []
    for slug in get_compare_slugs(session):
        product = local_store.get_product_by_slug(slug)
        if product:
            products.append(product)
    return products
