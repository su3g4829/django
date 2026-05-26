"""購物車服務模組。

負責在 session 中維護購物車內容、折扣碼與金額試算結果。
"""
from __future__ import annotations
from typing import Dict, Any, Optional

from decimal import Decimal

CART_KEY = "cart"


def _ensure_cart(session) -> Dict[str, Any]:
    """確保 購物車 所需的基礎資料結構已存在。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。

    回傳:
        依函式用途回傳對應資料。
    """
    cart = session.get(CART_KEY)
    if not cart or not isinstance(cart, dict):
        cart = {"items": {}, "coupon": None}
        session[CART_KEY] = cart
        session.modified = True
    # 兼容舊格式
    cart.setdefault("items", {})
    cart.setdefault("coupon", None)
    return cart


def get_cart(session) -> Dict[str, Any]:
    """取得 購物車 流程中指定條件的資料。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    return _ensure_cart(session)


def make_item_key(slug: str, variant_id: str = "") -> str:
    """處理 購物車 相關流程。

    參數:
        slug: 商品或頁面使用的網址識別字串。
        variant_id: 指定變體的唯一識別字串。

    回傳:
        依函式用途回傳對應資料。
    """
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
    """把商品加入購物車，必要時與既有品項合併數量。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。
        id: 函式執行所需的輸入資料。
        slug: 商品或頁面使用的網址識別字串。
        name: 名稱字串，可能是商品名稱、變體名稱或檔名來源。
        price: 函式執行所需的輸入資料。
        qty: 品項數量。
        variant_id: 指定變體的唯一識別字串。
        variant_name: 函式執行所需的輸入資料。
        sku: 庫存管理單位，用來區分商品變體。

    回傳:
        無回傳值；函式會直接修改 session、檔案或傳入資料。
    """
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
    """更新既有 購物車 資料。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。
        item_key: 購物車品項鍵值，用來區分 slug 與變體組合。
        qty: 品項數量。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    cart = _ensure_cart(session)
    items = cart["items"]
    if item_key in items:
        if qty <= 0:
            del items[item_key]
        else:
            items[item_key]["qty"] = qty
        session.modified = True


def remove_item(session, item_key: str) -> None:
    """處理 購物車 相關流程。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。
        item_key: 購物車品項鍵值，用來區分 slug 與變體組合。

    回傳:
        無回傳值；函式會直接修改 session、檔案或傳入資料。
    """
    cart = _ensure_cart(session)
    if item_key in cart["items"]:
        del cart["items"][item_key]
        session.modified = True


def clear(session) -> None:
    """處理 購物車 相關流程。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。

    回傳:
        無回傳值；函式會直接修改 session、檔案或傳入資料。
    """
    session[CART_KEY] = {"items": {}, "coupon": None}
    session.modified = True


# ==== 價格與折扣規則（示範） ====
SHIPPING_FEE = Decimal("60.0")        # 運費 60（滿額免運）
FREE_SHIPPING_THRESHOLD = Decimal("1000.0")
COUPONS = {
    "SAVE10": Decimal("0.10"),        # 9折（打 10% off）
}


def compute_totals(session) -> Dict[str, Decimal]:
    """計算購物車小計、運費、折扣與總金額。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。

    回傳:
        依函式用途回傳對應資料。
    """
    cart = _ensure_cart(session)
    subtotal = sum((Decimal(str(i["price"])) * i["qty"] for i in cart["items"].values()), Decimal("0.0"))

    # 運費規則：滿額免運
    shipping = Decimal("0.0") if subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE if subtotal > 0 else Decimal("0.0")

    # 折扣規則：符合的話以百分比折抵
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
    """驗證並套用折扣碼，或在傳入空值時清除折扣碼。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。
        code: 折扣碼字串；空值通常代表清除折扣碼。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    cart = _ensure_cart(session)
    if not code:
        cart["coupon"] = None
        session.modified = True
        return False
    code = code.strip().upper()
    if code in COUPONS:
        cart["coupon"] = code
        session.modified = True
        return True
    return False


def count_items(session) -> int:
    """處理 購物車 相關流程。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。

    回傳:
        數值結果，供後續金額或庫存流程使用。
    """
    cart = _ensure_cart(session)
    return sum(i["qty"] for i in cart["items"].values())
