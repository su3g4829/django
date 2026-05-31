"""Session-backed cart helpers.

The cart is stored in the Django session and scoped to the currently logged-in
demo user. Different accounts using the same browser should not see each
other's cart contents.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

CART_KEY = "cart"
SESSION_USER_KEY = "demo_user"
GUEST_BUCKET_KEY = "__guest__"

# Legacy single-seller defaults kept for coupon math; checkout shipping now
# comes from order_service and seller/product shipping rules.
SHIPPING_FEE = Decimal("60.0")
FREE_SHIPPING_THRESHOLD = Decimal("1000.0")
COUPONS = {
    "SAVE10": Decimal("0.10"),
}


def _session_bucket_name(session) -> str:
    user = session.get(SESSION_USER_KEY)
    if isinstance(user, dict):
        username = str(user.get("username", "")).strip().lower()
        if username:
            return username
    return GUEST_BUCKET_KEY


def _normalize_cart_map(session) -> Dict[str, Any]:
    raw = session.get(CART_KEY)
    if not isinstance(raw, dict):
        raw = {}
        session[CART_KEY] = raw
        session.modified = True
        return raw

    # Older sessions stored a single cart dict directly under "cart".
    if "items" in raw or "coupon" in raw:
        raw = {GUEST_BUCKET_KEY: raw}
        session[CART_KEY] = raw
        session.modified = True
        return raw

    return raw


def _ensure_cart(session) -> Dict[str, Any]:
    cart_map = _normalize_cart_map(session)
    bucket_name = _session_bucket_name(session)
    cart = cart_map.get(bucket_name)
    if not isinstance(cart, dict):
        cart = {"items": {}, "coupon": None}
        cart_map[bucket_name] = cart
        session[CART_KEY] = cart_map
        session.modified = True
    cart.setdefault("items", {})
    cart.setdefault("coupon", None)
    return cart


def get_cart(session) -> Dict[str, Any]:
    return _ensure_cart(session)


def make_item_key(slug: str, variant_id: str = "") -> str:
    clean_variant_id = str(variant_id).strip()
    return f"{slug}__{clean_variant_id}" if clean_variant_id else slug


def add_item(
    session,
    *,
    id: int,
    slug: str,
    name: str,
    price: float,
    qty: int = 1,
    variant_id: str = "",
    variant_name: str = "",
    sku: str = "",
) -> None:
    if qty <= 0:
        return
    cart = _ensure_cart(session)
    items = cart["items"]
    item_key = make_item_key(slug, variant_id)
    if item_key in items:
        items[item_key]["qty"] += qty
    else:
        items[item_key] = {
            "key": item_key,
            "id": id,
            "slug": slug,
            "name": name,
            "display_name": f"{name} - {variant_name}" if variant_name else name,
            "price": float(price),
            "qty": qty,
            "variant_id": variant_id,
            "variant_name": variant_name,
            "sku": sku,
        }
    session.modified = True


def update_qty(session, item_key: str, qty: int) -> None:
    cart = _ensure_cart(session)
    items = cart["items"]
    if item_key in items:
        if qty <= 0:
            del items[item_key]
        else:
            items[item_key]["qty"] = qty
        session.modified = True


def remove_item(session, item_key: str) -> None:
    cart = _ensure_cart(session)
    if item_key in cart["items"]:
        del cart["items"][item_key]
        session.modified = True


def clear(session) -> None:
    cart_map = _normalize_cart_map(session)
    cart_map[_session_bucket_name(session)] = {"items": {}, "coupon": None}
    session[CART_KEY] = cart_map
    session.modified = True


def clear_guest_cart(session) -> None:
    cart_map = _normalize_cart_map(session)
    cart_map[GUEST_BUCKET_KEY] = {"items": {}, "coupon": None}
    session[CART_KEY] = cart_map
    session.modified = True


def migrate_guest_cart(session, username: str) -> None:
    cart_map = _normalize_cart_map(session)
    target_bucket = username.strip().lower()
    if not target_bucket:
        return

    guest_cart = cart_map.get(GUEST_BUCKET_KEY)
    if not isinstance(guest_cart, dict):
        guest_cart = {"items": {}, "coupon": None}
    target_cart = cart_map.get(target_bucket)
    if not isinstance(target_cart, dict):
        target_cart = {"items": {}, "coupon": None}

    guest_items = guest_cart.get("items", {})
    target_items = target_cart.setdefault("items", {})
    if isinstance(guest_items, dict):
        for item_key, guest_item in guest_items.items():
            if not isinstance(guest_item, dict):
                continue
            if item_key in target_items and isinstance(target_items[item_key], dict):
                target_items[item_key]["qty"] = int(target_items[item_key].get("qty", 0)) + int(guest_item.get("qty", 0))
            else:
                target_items[item_key] = dict(guest_item)

    if not target_cart.get("coupon") and guest_cart.get("coupon"):
        target_cart["coupon"] = guest_cart.get("coupon")
    else:
        target_cart.setdefault("coupon", None)

    cart_map[target_bucket] = target_cart
    cart_map[GUEST_BUCKET_KEY] = {"items": {}, "coupon": None}
    session[CART_KEY] = cart_map
    session.modified = True


def compute_totals(session) -> Dict[str, Decimal]:
    cart = _ensure_cart(session)
    subtotal = sum((Decimal(str(item["price"])) * item["qty"] for item in cart["items"].values()), Decimal("0.0"))
    shipping = Decimal("0.0") if subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE if subtotal > 0 else Decimal("0.0")

    discount = Decimal("0.0")
    code = cart.get("coupon")
    if code and code in COUPONS and subtotal > 0:
        discount = (subtotal * COUPONS[code]).quantize(Decimal("0.01"))

    total = (subtotal + shipping - discount).quantize(Decimal("0.01"))
    return {
        "subtotal": subtotal.quantize(Decimal("0.01")),
        "shipping": shipping.quantize(Decimal("0.01")),
        "discount": discount,
        "total": total,
    }


def apply_coupon(session, code: Optional[str]) -> bool:
    cart = _ensure_cart(session)
    if not code:
        cart["coupon"] = None
        session.modified = True
        return False
    clean_code = code.strip().upper()
    if clean_code in COUPONS:
        cart["coupon"] = clean_code
        session.modified = True
        return True
    return False


def count_items(session) -> int:
    cart = _ensure_cart(session)
    return sum(item["qty"] for item in cart["items"].values())
