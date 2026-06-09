"""購物車服務模組。

目前正式資料來源如下：
- 訪客購物車：存在 Django session
- 已登入購物車：存在 ORM `Cart` / `CartItem`

即使登入後主資料在 ORM，session 仍保留一份鏡像 bucket，
用來維持目前前端與既有流程對 session cart payload 的相容性。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from django.db import transaction

from ..models import AppUser as AppUserModel
from ..models import Cart as CartModel
from ..models import CartItem as CartItemModel
from ..models import Product as ProductModel
from ..models import ProductVariant as ProductVariantModel

CART_KEY = "cart"
SESSION_USER_KEY = "demo_user"
GUEST_BUCKET_KEY = "__guest__"

# 這組運費與折扣常數只保留給舊版 `compute_totals(...)` 使用。
# 真正 checkout 的運費計算已改由 `order_service` 與賣家運費規則處理。
SHIPPING_FEE = Decimal("60.0")
FREE_SHIPPING_THRESHOLD = Decimal("1000.0")
COUPONS = {
    "SAVE10": Decimal("0.10"),
}


def _default_cart() -> Dict[str, Any]:
    """回傳 cart 的標準空結構。"""
    return {"items": {}, "coupon": None}


def _normalize_cart_payload(raw: Any) -> Dict[str, Any]:
    """把任意輸入正規化成 cart 標準結構。

    無論來源是 session 或 ORM，最終都要長成：
    - `items`: dict
    - `coupon`: str | None
    """

    if not isinstance(raw, dict):
        return _default_cart()
    items = raw.get("items")
    coupon = raw.get("coupon")
    return {
        "items": items if isinstance(items, dict) else {},
        "coupon": coupon,
    }


def _session_bucket_name(session) -> str:
    """回傳目前 session 應使用的 bucket 名稱。

    規則：
    - 已登入：使用 username 當 bucket key
    - 訪客：固定落在 `__guest__`
    """

    user = session.get(SESSION_USER_KEY)
    if isinstance(user, dict):
        username = str(user.get("username", "")).strip().lower()
        if username:
            return username
    return GUEST_BUCKET_KEY


def _logged_in_username(session) -> str:
    """回傳目前登入 username；訪客則回傳空字串。"""

    bucket_name = _session_bucket_name(session)
    return "" if bucket_name == GUEST_BUCKET_KEY else bucket_name


def _normalize_cart_map(session) -> Dict[str, Any]:
    """確保 session 內的 cart 容器是 bucket map 結構。

    新結構：
    - `cart[username]`
    - `cart["__guest__"]`

    舊 session 可能直接把單一購物車 dict 放在 `cart` 底下，
    這裡會順手升級成 bucket map。
    """

    raw = session.get(CART_KEY)
    if not isinstance(raw, dict):
        raw = {}
        session[CART_KEY] = raw
        session.modified = True
        return raw

    # 舊版 session 直接把單一 cart dict 塞在 `cart` 下，這裡統一轉成 guest bucket。
    if "items" in raw or "coupon" in raw:
        raw = {GUEST_BUCKET_KEY: _normalize_cart_payload(raw)}
        session[CART_KEY] = raw
        session.modified = True
        return raw

    return raw


def _ensure_guest_cart(session) -> Dict[str, Any]:
    """確保訪客 bucket 存在，且內容符合標準 cart 結構。"""

    cart_map = _normalize_cart_map(session)
    cart = cart_map.get(GUEST_BUCKET_KEY)
    normalized = _normalize_cart_payload(cart)
    if cart != normalized:
        cart_map[GUEST_BUCKET_KEY] = normalized
        session[CART_KEY] = cart_map
        session.modified = True
    return normalized


def _db_cart_enabled() -> bool:
    """判斷第二波購物車 ORM 表是否已可用。"""

    try:
        CartModel.objects.count()
        return True
    except Exception:
        return False


def _get_or_bootstrap_db_user(username: str) -> Optional[AppUserModel]:
    """取得對應的 ORM 會員；必要時自動補建。

    購物車 ORM 需要先有 `AppUser` 列，所以這裡會確保對應會員存在。
    """

    clean_username = str(username or "").strip().lower()
    if not clean_username or not _db_cart_enabled():
        return None
    db_user = AppUserModel.objects.filter(username=clean_username).first()
    if db_user:
        return db_user

    from . import auth_demo

    return auth_demo._get_or_bootstrap_db_user(clean_username)


def _resolve_product_variant(product: ProductModel, variant_id: str) -> Optional[ProductVariantModel]:
    """把 cart 的公開 variant id 對應到 ORM 變體列。"""

    clean_variant_id = str(variant_id or "").strip()
    if not clean_variant_id:
        return None
    variant = ProductVariantModel.objects.filter(product=product, external_variant_id=clean_variant_id).first()
    if variant:
        return variant
    if clean_variant_id.isdigit():
        return ProductVariantModel.objects.filter(product=product, id=int(clean_variant_id)).first()
    return None


def _line_variant_id(item: CartItemModel) -> str:
    """回傳 cart API payload 要公開使用的 variant id。

    優先順序：
    - `product_variant.external_variant_id`
    - 從 `item_key` 反推
    """

    if item.product_variant_id and item.product_variant and item.product_variant.external_variant_id:
        return str(item.product_variant.external_variant_id)
    key = str(item.item_key or "")
    if "__" in key:
        return key.split("__", 1)[1]
    return ""


def _db_cart_to_payload(db_cart: CartModel) -> Dict[str, Any]:
    """把 ORM cart 列序列化成目前 API / session 共用的 payload。"""

    payload = _default_cart()
    payload["coupon"] = db_cart.coupon_code or None
    items: Dict[str, Any] = {}
    queryset = db_cart.items.select_related("product", "product_variant").order_by("id")
    for line in queryset:
        variant_id = _line_variant_id(line)
        variant_name = str(line.variant_name_snapshot or "")
        name = str(line.product_name_snapshot or (line.product.name if line.product_id else ""))
        items[line.item_key] = {
            "key": line.item_key,
            "id": line.product_id,
            "slug": str(line.product.slug if line.product_id else ""),
            "name": name,
            "display_name": f"{name} - {variant_name}" if variant_name else name,
            "price": float(line.unit_price_snapshot),
            "qty": int(line.quantity),
            "variant_id": variant_id,
            "variant_name": variant_name,
            "sku": str(line.sku_snapshot or ""),
        }
    payload["items"] = items
    return payload


@transaction.atomic
def _replace_db_cart_from_payload(db_cart: CartModel, cart: Dict[str, Any]) -> Dict[str, Any]:
    """用標準 cart payload 完整覆蓋 ORM cart 內容。

    這個 helper 主要用在：
    - guest cart 併入登入購物車後回寫 ORM
    - 每次更新登入 cart 時，把目前有效狀態同步到 ORM
    """

    normalized = _normalize_cart_payload(cart)
    db_cart.coupon_code = str(normalized.get("coupon") or "")
    db_cart.save(update_fields=["coupon_code", "updated_at"])
    db_cart.items.all().delete()

    items = normalized.get("items", {})
    if isinstance(items, dict):
        for item_key, item in items.items():
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug") or "").strip()
            if not slug:
                continue
            product = ProductModel.objects.filter(slug=slug).first()
            if not product:
                product = ProductModel.objects.filter(id=item.get("id")).first()
            if not product:
                continue
            variant_id = str(item.get("variant_id") or "").strip()
            variant = _resolve_product_variant(product, variant_id)
            name = str(item.get("name") or product.name)
            variant_name = str(item.get("variant_name") or "")
            CartItemModel.objects.create(
                cart=db_cart,
                product=product,
                product_variant=variant,
                item_key=str(item_key),
                quantity=max(int(item.get("qty") or 0), 1),
                unit_price_snapshot=Decimal(str(item.get("price") or product.price)),
                product_name_snapshot=name,
                variant_name_snapshot=variant_name,
                sku_snapshot=str(item.get("sku") or (variant.sku if variant else "")),
            )
    db_cart.refresh_from_db()
    return _db_cart_to_payload(db_cart)


def _get_or_create_db_cart(username: str) -> Optional[CartModel]:
    """取得或建立登入會員對應的 ORM 購物車。"""

    db_user = _get_or_bootstrap_db_user(username)
    if not db_user:
        return None
    db_cart, _ = CartModel.objects.get_or_create(user=db_user, defaults={"coupon_code": ""})
    return db_cart


def _bootstrap_db_cart_from_legacy(username: str, db_cart: CartModel) -> None:
    """保留舊介面的相容 hook；目前不再從其他來源匯入購物車。"""

    return


def _get_persisted_user_cart(username: str) -> Dict[str, Any]:
    """讀取登入會員的持久化購物車。

    優先順序：
    - ORM cart
    - 空 cart
    """

    clean_username = str(username or "").strip().lower()
    if not clean_username:
        return _default_cart()
    db_cart = _get_or_create_db_cart(clean_username)
    if not db_cart:
        return _default_cart()
    _bootstrap_db_cart_from_legacy(clean_username, db_cart)
    return _db_cart_to_payload(db_cart)


def _save_persisted_user_cart(username: str, cart: Dict[str, Any]) -> Dict[str, Any]:
    """保存登入會員購物車，優先寫入 ORM。"""

    clean_username = str(username or "").strip().lower()
    normalized = _normalize_cart_payload(cart)
    if not clean_username:
        return normalized
    db_cart = _get_or_create_db_cart(clean_username)
    if not db_cart:
        return normalized
    return _replace_db_cart_from_payload(db_cart, normalized)


def _sync_session_bucket(session, bucket_name: str, cart: Dict[str, Any]) -> None:
    """把 cart payload 鏡像同步回 session bucket。

    即使登入後真正主資料在 ORM，session 還是保留一份，
    讓目前前端與既有 middleware / helper 能維持相容。
    """

    cart_map = _normalize_cart_map(session)
    cart_map[bucket_name] = _normalize_cart_payload(cart)
    session[CART_KEY] = cart_map
    session.modified = True


def _read_active_cart(session) -> Dict[str, Any]:
    """讀取目前有效 cart。

    規則：
    - 已登入：讀持久化 cart，並同步回 session bucket
    - 訪客：直接讀 guest bucket
    """

    username = _logged_in_username(session)
    if username:
        cart = _get_persisted_user_cart(username)
        _sync_session_bucket(session, username, cart)
        return cart
    return _ensure_guest_cart(session)


def _write_active_cart(session, cart: Dict[str, Any]) -> Dict[str, Any]:
    """寫入目前有效 cart。

    規則：
    - 已登入：先寫持久化 cart，再同步 session bucket
    - 訪客：只更新 guest bucket
    """

    username = _logged_in_username(session)
    normalized = _normalize_cart_payload(cart)
    if username:
        normalized = _save_persisted_user_cart(username, normalized)
        _sync_session_bucket(session, username, normalized)
        return normalized
    _sync_session_bucket(session, GUEST_BUCKET_KEY, normalized)
    return normalized


def get_cart(session) -> Dict[str, Any]:
    """回傳目前會員或訪客的有效購物車。"""

    return _read_active_cart(session)


def make_item_key(slug: str, variant_id: str = "") -> str:
    """由商品 slug 與 variant id 組出穩定的 cart line key。"""

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
    """加入一筆商品到購物車。

    若同一個 `item_key` 已存在，則直接累加數量，而不是新增第二列。
    """

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
    """更新單一 cart line 數量；`qty <= 0` 時直接移除。"""

    cart = _read_active_cart(session)
    items = cart["items"]
    if item_key in items:
        if qty <= 0:
            del items[item_key]
        else:
            items[item_key]["qty"] = qty
        _write_active_cart(session, cart)


def remove_item(session, item_key: str) -> None:
    """刪除單一購物車品項。"""

    cart = _read_active_cart(session)
    if item_key in cart["items"]:
        del cart["items"][item_key]
        _write_active_cart(session, cart)


def clear(session) -> None:
    """清空目前有效 cart bucket。"""

    _write_active_cart(session, _default_cart())


def clear_guest_cart(session) -> None:
    """清空訪客 bucket，不影響已登入使用者的持久化 cart。"""

    _sync_session_bucket(session, GUEST_BUCKET_KEY, _default_cart())


def migrate_guest_cart(session, username: str) -> None:
    """把訪客購物車併入登入會員的持久化 cart。

    常見於：
    - 使用者先以訪客身分加商品
    - 登入後希望保留先前加入的品項與折扣碼
    """

    target_bucket = str(username or "").strip().lower()
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
            # 同 key 商品直接累加數量，避免 guest 與 member cart 各留一列重複項目。
            if item_key in target_items and isinstance(target_items[item_key], dict):
                target_items[item_key]["qty"] = int(target_items[item_key].get("qty", 0)) + int(guest_item.get("qty", 0))
            else:
                target_items[item_key] = dict(guest_item)

    if not target_cart.get("coupon") and guest_cart.get("coupon"):
        target_cart["coupon"] = guest_cart.get("coupon")
    else:
        target_cart.setdefault("coupon", None)

    persisted = _save_persisted_user_cart(target_bucket, target_cart)
    _sync_session_bucket(session, target_bucket, persisted)
    _sync_session_bucket(session, GUEST_BUCKET_KEY, _default_cart())


def compute_totals(session) -> Dict[str, Decimal]:
    """計算舊版 cart totals。

    注意：
    - 這不是 checkout 最終金額邏輯
    - 主要保留給舊流程與簡化場景使用
    """

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
    """套用或清除目前 cart 的折扣碼。

    回傳值語意：
    - `True`：成功套用有效折扣碼
    - `False`：清除折扣碼，或輸入了無效代碼
    """

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
    """回傳所有 cart line 的總件數。"""

    cart = _read_active_cart(session)
    return sum(item["qty"] for item in cart["items"].values())
