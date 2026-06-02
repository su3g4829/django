"""購物車 service，採用訪客 session + 會員持久化混合模式。

目前規則：
- 未登入訪客使用 Django session
- 已登入會員將 cart 持久化到本地 user store

用途：
- 支援購物車 CRUD
- 支援登入時把訪客 cart 合併到會員 cart
- 未來可平滑遷移到真正的資料庫 `Cart` / `CartItem` model
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any, Dict, Optional

from ..repositories import local_store

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


# cart 基本結構：
# - `items`: 以 item_key 為 key 的購物車項目 map
# - `coupon`: 目前套用的折扣碼
def _default_cart() -> Dict[str, Any]:
    return {"items": {}, "coupon": None}


def _normalize_cart_payload(raw: Any) -> Dict[str, Any]:
    """把任意輸入整理成一致的 cart payload 結構。"""

    if not isinstance(raw, dict):
        return _default_cart()
    items = raw.get("items")
    coupon = raw.get("coupon")
    return {
        "items": items if isinstance(items, dict) else {},
        "coupon": coupon,
    }


def _session_bucket_name(session) -> str:
    """依 session 內 demo_user 決定目前要讀寫哪個 bucket。"""

    user = session.get(SESSION_USER_KEY)
    if isinstance(user, dict):
        username = str(user.get("username", "")).strip().lower()
        if username:
            return username
    return GUEST_BUCKET_KEY


def _logged_in_username(session) -> str:
    """取得目前登入會員的 username；若為訪客則回空字串。"""

    bucket_name = _session_bucket_name(session)
    return "" if bucket_name == GUEST_BUCKET_KEY else bucket_name


def _normalize_cart_map(session) -> Dict[str, Any]:
    """確保 session 內的 cart 容器是 bucket map 格式。"""

    raw = session.get(CART_KEY)
    if not isinstance(raw, dict):
        raw = {}
        session[CART_KEY] = raw
        session.modified = True
        return raw

    # Older sessions stored a single cart dict directly under "cart".
    if "items" in raw or "coupon" in raw:
        raw = {GUEST_BUCKET_KEY: _normalize_cart_payload(raw)}
        session[CART_KEY] = raw
        session.modified = True
        return raw

    return raw


def _ensure_guest_cart(session) -> Dict[str, Any]:
    """確保訪客 bucket 的 cart 存在且結構正確。"""

    cart_map = _normalize_cart_map(session)
    cart = cart_map.get(GUEST_BUCKET_KEY)
    normalized = _normalize_cart_payload(cart)
    if cart != normalized:
        cart_map[GUEST_BUCKET_KEY] = normalized
        session[CART_KEY] = cart_map
        session.modified = True
    return normalized


def _get_persisted_user_cart(username: str) -> Dict[str, Any]:
    """從本地 user store 讀取會員持久化 cart。"""

    user = local_store.get_user_by_username(username)
    if not user:
        return _default_cart()
    return _normalize_cart_payload(user.get("cart"))


def _save_persisted_user_cart(username: str, cart: Dict[str, Any]) -> Dict[str, Any]:
    """把會員 cart 寫回本地 user store。"""

    clean_username = username.strip().lower()
    users = deepcopy(local_store.get_users())
    normalized = _normalize_cart_payload(cart)
    for item in users:
        if str(item.get("username", "")).strip().lower() != clean_username:
            continue
        item["cart"] = normalized
        local_store.save_users(users)
        return normalized
    return normalized


def _sync_session_bucket(session, bucket_name: str, cart: Dict[str, Any]) -> None:
    """把某個 bucket 的 cart 狀態同步回 session。"""

    cart_map = _normalize_cart_map(session)
    cart_map[bucket_name] = _normalize_cart_payload(cart)
    session[CART_KEY] = cart_map
    session.modified = True


def _read_active_cart(session) -> Dict[str, Any]:
    """讀取目前有效的 cart；會員優先走持久化 cart。"""

    username = _logged_in_username(session)
    if username:
        cart = _get_persisted_user_cart(username)
        _sync_session_bucket(session, username, cart)
        return cart
    return _ensure_guest_cart(session)


def _write_active_cart(session, cart: Dict[str, Any]) -> Dict[str, Any]:
    """寫入目前有效的 cart；會員同步寫入持久化 store。"""

    username = _logged_in_username(session)
    normalized = _normalize_cart_payload(cart)
    if username:
        normalized = _save_persisted_user_cart(username, normalized)
        _sync_session_bucket(session, username, normalized)
        return normalized
    _sync_session_bucket(session, GUEST_BUCKET_KEY, normalized)
    return normalized


def get_cart(session) -> Dict[str, Any]:
    """取得目前使用者 / 訪客的有效購物車。"""

    return _read_active_cart(session)


def make_item_key(slug: str, variant_id: str = "") -> str:
    """用商品 slug 與 variant id 產生購物車 item key。"""

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
    """加入商品到購物車；同 key 已存在時累加數量。"""

    if qty <= 0:
        return
    cart = _read_active_cart(session)
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
    _write_active_cart(session, cart)


def update_qty(session, item_key: str, qty: int) -> None:
    """更新購物車單項數量；小於等於 0 時直接刪除。"""

    cart = _read_active_cart(session)
    items = cart["items"]
    if item_key in items:
        if qty <= 0:
            del items[item_key]
        else:
            items[item_key]["qty"] = qty
        _write_active_cart(session, cart)


def remove_item(session, item_key: str) -> None:
    """刪除購物車單項。"""

    cart = _read_active_cart(session)
    if item_key in cart["items"]:
        del cart["items"][item_key]
        _write_active_cart(session, cart)


def clear(session) -> None:
    """清空目前有效 bucket 的購物車。"""

    _write_active_cart(session, _default_cart())


def clear_guest_cart(session) -> None:
    """清空訪客 bucket 的購物車。"""

    _sync_session_bucket(session, GUEST_BUCKET_KEY, _default_cart())


def migrate_guest_cart(session, username: str) -> None:
    """登入時把訪客 cart 合併到指定會員的持久化 cart。"""

    target_bucket = username.strip().lower()
    if not target_bucket:
        return

    guest_cart = _ensure_guest_cart(session)
    target_cart = _get_persisted_user_cart(target_bucket)

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

    _save_persisted_user_cart(target_bucket, target_cart)
    _sync_session_bucket(session, target_bucket, target_cart)
    _sync_session_bucket(session, GUEST_BUCKET_KEY, _default_cart())


def compute_totals(session) -> Dict[str, Decimal]:
    """依 legacy coupon / shipping 規則計算購物車金額摘要。"""

    cart = _read_active_cart(session)
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
    """套用或清除購物車折扣碼。"""

    cart = _read_active_cart(session)
    if not code:
        cart["coupon"] = None
        _write_active_cart(session, cart)
        return False
    clean_code = code.strip().upper()
    if clean_code in COUPONS:
        cart["coupon"] = clean_code
        _write_active_cart(session, cart)
        return True
    return False


def count_items(session) -> int:
    """計算目前有效購物車中的商品總件數。"""

    cart = _read_active_cart(session)
    return sum(item["qty"] for item in cart["items"].values())
