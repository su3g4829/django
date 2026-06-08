"""Local JSON-backed data access helpers.

This module centralizes reads and writes under `data/*.json` so service and
API layers do not touch files directly.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.conf import settings

_TTL_SECONDS = 5
_cache: Dict[str, dict] = {}
_lock = threading.Lock()


def _data_dir() -> Path:
    """Return the local JSON data directory."""
    return Path(settings.BASE_DIR) / "data"


def _load_json(name: str) -> Any:
    """Load one JSON file and return the decoded Python object."""
    path = _data_dir() / name
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def _write_json(name: str, data: Any) -> None:
    """Write one Python object back to a JSON file."""
    path = _data_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _cached(key: str, loader):
    """Read from cache, or reload when the cached value is stale."""
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit["ts"] < _TTL_SECONDS:
            return hit["val"]

    value = loader()

    with _lock:
        _cache[key] = {"val": value, "ts": now}
    return value


def _invalidate(key: str) -> None:
    """Remove one cached entry."""
    with _lock:
        _cache.pop(key, None)


def clear_cache() -> None:
    """Clear all cached local data."""
    with _lock:
        _cache.clear()


def _default_invoice_profile() -> Dict[str, Any]:
    """Return the normalized invoice profile shape."""
    return {
        "invoice_type": "personal",
        "carrier_code": "",
        "company_name": "",
        "tax_id": "",
        "updated_at": "",
    }


def _default_shipping_rules() -> Dict[str, Any]:
    """Return seller-level shipping defaults for marketplace checkout."""
    return {
        "home_delivery_enabled": True,
        "home_delivery_fee": "80.00",
        "convenience_store_enabled": True,
        "convenience_store_fee": "60.00",
        "free_shipping_threshold": "1200.00",
    }


def _default_cart() -> Dict[str, Any]:
    """Return the normalized cart payload shape."""
    return {
        "items": {},
        "coupon": None,
    }


def _default_categories() -> List[Dict[str, Any]]:
    """Return the built-in product category master seed."""
    return [
        {
            "id": 1,
            "slug": "tops",
            "name": "上衣",
            "description": "",
            "is_active": True,
            "sort_order": 1,
            "created_at": "2026-06-02T00:00:00+08:00",
            "updated_at": "2026-06-02T00:00:00+08:00",
        },
        {
            "id": 2,
            "slug": "pants",
            "name": "褲子",
            "description": "",
            "is_active": True,
            "sort_order": 2,
            "created_at": "2026-06-02T00:00:00+08:00",
            "updated_at": "2026-06-02T00:00:00+08:00",
        },
    ]


def _normalize_user_record(user: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one stored user record into the expected runtime shape."""
    normalized = dict(user)
    username = str(normalized.get("username", "")).strip().lower()
    normalized["username"] = username
    normalized["display_name"] = str(normalized.get("display_name") or username)
    normalized["role"] = str(normalized.get("role") or "member")
    normalized["account_status"] = str(normalized.get("account_status") or "active")
    normalized["seller_request_status"] = str(normalized.get("seller_request_status") or "")
    normalized["email"] = str(normalized.get("email") or "")
    normalized["created_at"] = str(normalized.get("created_at") or "")
    normalized["updated_at"] = str(normalized.get("updated_at") or normalized["created_at"] or "")
    normalized["last_login_at"] = str(normalized.get("last_login_at") or "")
    normalized["seller_requested_at"] = str(normalized.get("seller_requested_at") or "")
    normalized["seller_reviewed_at"] = str(normalized.get("seller_reviewed_at") or "")
    normalized["account_status_updated_at"] = str(normalized.get("account_status_updated_at") or "")
    addresses = normalized.get("addresses")
    normalized["addresses"] = addresses if isinstance(addresses, list) else []
    normalized["default_address_id"] = normalized.get("default_address_id")

    invoice_profile = normalized.get("invoice_profile")
    merged_invoice = _default_invoice_profile()
    if isinstance(invoice_profile, dict):
        merged_invoice.update(invoice_profile)
    normalized["invoice_profile"] = merged_invoice

    shipping_rules = normalized.get("shipping_rules")
    merged_shipping_rules = _default_shipping_rules()
    if isinstance(shipping_rules, dict):
        merged_shipping_rules.update(shipping_rules)
    normalized["shipping_rules"] = merged_shipping_rules

    cart = normalized.get("cart")
    merged_cart = _default_cart()
    if isinstance(cart, dict):
        items = cart.get("items")
        if isinstance(items, dict):
            merged_cart["items"] = items
        merged_cart["coupon"] = cart.get("coupon")
    normalized["cart"] = merged_cart
    return normalized


def get_products() -> List[Dict[str, Any]]:
    return _cached("products", lambda: _load_json("products.json"))


def get_product_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    for product in get_products():
        if product.get("slug") == slug:
            return product
    return None


def get_product_by_id(product_id: int) -> Optional[Dict[str, Any]]:
    for product in get_products():
        if product.get("id") == product_id:
            return product
    return None


def save_products(products: List[Dict[str, Any]]) -> None:
    _write_json("products.json", products)
    _invalidate("products")


def get_categories() -> List[Dict[str, Any]]:
    try:
        return _cached("categories", lambda: _load_json("categories.json"))
    except FileNotFoundError:
        return _default_categories()


def get_category_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    clean_slug = slug.strip().lower()
    for category in get_categories():
        if str(category.get("slug") or "").strip().lower() == clean_slug:
            return category
    return None


def save_categories(categories: List[Dict[str, Any]]) -> None:
    _write_json("categories.json", categories)
    _invalidate("categories")


def get_reviews() -> List[Dict[str, Any]]:
    try:
        return _cached("reviews", lambda: _load_json("reviews.json"))
    except FileNotFoundError:
        return []


def get_reviews_by_product_id(product_id: int) -> List[Dict[str, Any]]:
    reviews = [review for review in get_reviews() if review.get("product_id") == product_id]
    return sorted(reviews, key=lambda item: item.get("created_at", ""), reverse=True)


def save_reviews(reviews: List[Dict[str, Any]]) -> None:
    _write_json("reviews.json", reviews)
    _invalidate("reviews")


def get_recommendations() -> List[Dict[str, Any]]:
    try:
        return _cached("recommendations", lambda: _load_json("recommendations.json"))
    except FileNotFoundError:
        return []


def get_recommendation_config(product_id: int) -> Optional[Dict[str, Any]]:
    for item in get_recommendations():
        if item.get("product_id") == product_id:
            return item
    return None


def get_questions() -> List[Dict[str, Any]]:
    try:
        return _cached("questions", lambda: _load_json("questions.json"))
    except FileNotFoundError:
        return []


def get_questions_by_product_id(product_id: int) -> List[Dict[str, Any]]:
    questions = [item for item in get_questions() if item.get("product_id") == product_id]
    return sorted(questions, key=lambda item: item.get("created_at", ""), reverse=True)


def save_questions(questions: List[Dict[str, Any]]) -> None:
    _write_json("questions.json", questions)
    _invalidate("questions")


def get_competitor_prices() -> List[Dict[str, Any]]:
    try:
        return _cached("competitor_prices", lambda: _load_json("competitor_prices.json"))
    except FileNotFoundError:
        return []


def save_competitor_prices(items: List[Dict[str, Any]]) -> None:
    _write_json("competitor_prices.json", items)
    _invalidate("competitor_prices")


def get_newebpay_payment_logs() -> List[Dict[str, Any]]:
    try:
        return _cached("newebpay_payment_logs", lambda: _load_json("newebpay_payment_logs.json"))
    except FileNotFoundError:
        return []


def save_newebpay_payment_logs(items: List[Dict[str, Any]]) -> None:
    _write_json("newebpay_payment_logs.json", items)
    _invalidate("newebpay_payment_logs")


def get_newebpay_store_map_selections() -> List[Dict[str, Any]]:
    """Return persisted NewebPay convenience-store map selections."""
    try:
        return _cached("newebpay_store_map_selections", lambda: _load_json("newebpay_store_map_selections.json"))
    except FileNotFoundError:
        return []


def save_newebpay_store_map_selections(items: List[Dict[str, Any]]) -> None:
    """Persist NewebPay convenience-store map selections."""
    _write_json("newebpay_store_map_selections.json", items)
    _invalidate("newebpay_store_map_selections")


def get_posts() -> List[Dict[str, Any]]:
    try:
        return _cached("posts", lambda: _load_json("posts.json"))
    except FileNotFoundError:
        return []


def get_post_by_id(post_id: int) -> Optional[Dict[str, Any]]:
    for post in get_posts():
        if post.get("id") == post_id:
            return post
    return None


def save_posts(posts: List[Dict[str, Any]]) -> None:
    _write_json("posts.json", posts)
    _invalidate("posts")


def get_banners() -> List[Dict[str, Any]]:
    try:
        return _cached("banners", lambda: _load_json("banners.json"))
    except FileNotFoundError:
        return []


def save_banners(banners: List[Dict[str, Any]]) -> None:
    _write_json("banners.json", banners)
    _invalidate("banners")


def get_users() -> List[Dict[str, Any]]:
    try:
        return _cached("users", lambda: [_normalize_user_record(item) for item in _load_json("users.json")])
    except FileNotFoundError:
        return []


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    clean_username = username.strip().lower()
    for user in get_users():
        if user.get("username") == clean_username:
            return user
    return None


def save_users(users: List[Dict[str, Any]]) -> None:
    normalized = [_normalize_user_record(item) for item in users]
    _write_json("users.json", normalized)
    _invalidate("users")


def get_password_reset_tokens() -> List[Dict[str, Any]]:
    try:
        return _cached("password_reset_tokens", lambda: _load_json("password_reset_tokens.json"))
    except FileNotFoundError:
        return []


def save_password_reset_tokens(tokens: List[Dict[str, Any]]) -> None:
    _write_json("password_reset_tokens.json", tokens)
    _invalidate("password_reset_tokens")


def get_orders() -> List[Dict[str, Any]]:
    try:
        return _cached("orders", lambda: _load_json("orders.json"))
    except FileNotFoundError:
        return []


def get_order_by_id(order_id: int) -> Optional[Dict[str, Any]]:
    for order in get_orders():
        if order.get("id") == order_id:
            return order
    return None


def get_orders_by_username(username: str) -> List[Dict[str, Any]]:
    orders = [order for order in get_orders() if order.get("username") == username]
    return sorted(orders, key=lambda item: item.get("created_at", ""), reverse=True)


def save_orders(orders: List[Dict[str, Any]]) -> None:
    _write_json("orders.json", orders)
    _invalidate("orders")
