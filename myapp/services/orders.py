"""訂單與售後流程服務模組。

涵蓋建立訂單、買家查詢、賣家履約、售後申請與管理端審核等流程。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from ..repositories import local_store
from . import auth_demo
from . import cart as cart_service
from . import customer_center
from . import product_management

ORDER_STATUS_CONFIRMED = "confirmed"
ORDER_STATUS_CANCELLED = "cancelled"
ORDER_STATUS_REFUNDED = "refunded"
ORDER_STATUS_LABELS = {
    ORDER_STATUS_CONFIRMED: "已成立",
    ORDER_STATUS_CANCELLED: "已取消",
    ORDER_STATUS_REFUNDED: "已退款",
}

SERVICE_REQUEST_CANCEL = "cancel"
SERVICE_REQUEST_REFUND = "refund"
SERVICE_REQUEST_PENDING = "pending"
SERVICE_REQUEST_APPROVED = "approved"
SERVICE_REQUEST_REJECTED = "rejected"
SERVICE_REQUEST_TYPE_LABELS = {
    SERVICE_REQUEST_CANCEL: "取消訂單",
    SERVICE_REQUEST_REFUND: "退款申請",
}
SERVICE_REQUEST_STATUS_LABELS = {
    SERVICE_REQUEST_PENDING: "待審核",
    SERVICE_REQUEST_APPROVED: "已核准",
    SERVICE_REQUEST_REJECTED: "已駁回",
}

SELLER_STATUS_PENDING = "pending_shipment"
SELLER_STATUS_SHIPPED = "shipped"
SELLER_STATUS_COMPLETED = "completed"
SELLER_STATUS_CHOICES = [
    {"value": SELLER_STATUS_PENDING, "label": "待出貨"},
    {"value": SELLER_STATUS_SHIPPED, "label": "已出貨"},
    {"value": SELLER_STATUS_COMPLETED, "label": "已完成"},
]
SELLER_STATUS_LABELS = {item["value"]: item["label"] for item in SELLER_STATUS_CHOICES}

SHIPPING_METHOD_HOME_DELIVERY = "home_delivery"
SHIPPING_METHOD_CONVENIENCE_STORE = "convenience_store"
SHIPPING_METHOD_CHOICES = [
    {"value": SHIPPING_METHOD_HOME_DELIVERY, "label": "宅配到府"},
    {"value": SHIPPING_METHOD_CONVENIENCE_STORE, "label": "超商取貨"},
]
SHIPPING_METHOD_LABELS = {item["value"]: item["label"] for item in SHIPPING_METHOD_CHOICES}
LOGISTICS_CHECKOUT_ENABLED = True

PAYMENT_METHOD_NEWEBPAY = "newebpay"
PAYMENT_METHOD_NEWEBPAY_CREDIT = "newebpay_credit"
PAYMENT_METHOD_NEWEBPAY_GOOGLE_PAY = "newebpay_google_pay"
PAYMENT_METHOD_NEWEBPAY_SAMSUNG_PAY = "newebpay_samsung_pay"
PAYMENT_METHOD_NEWEBPAY_WEBATM = "newebpay_webatm"
PAYMENT_METHOD_NEWEBPAY_ATM = "newebpay_atm"
PAYMENT_METHOD_NEWEBPAY_CVS = "newebpay_cvs"
PAYMENT_METHOD_NEWEBPAY_BARCODE = "newebpay_barcode"
PAYMENT_METHOD_NEWEBPAY_CVSCOM = "newebpay_cvscom"
PAYMENT_METHOD_CHOICES = [
    {"value": PAYMENT_METHOD_NEWEBPAY, "label": "藍新支付"},
]
PAYMENT_METHOD_LABELS = {
    item["value"]: item["label"] for item in PAYMENT_METHOD_CHOICES
} | {
    PAYMENT_METHOD_NEWEBPAY_CREDIT: "藍新信用卡",
    PAYMENT_METHOD_NEWEBPAY_WEBATM: "藍新 WebATM",
    PAYMENT_METHOD_NEWEBPAY_ATM: "藍新 ATM 轉帳",
    PAYMENT_METHOD_NEWEBPAY_CVS: "藍新超商代碼",
    PAYMENT_METHOD_NEWEBPAY_BARCODE: "藍新超商條碼",
    PAYMENT_METHOD_NEWEBPAY_CVSCOM: "藍新超商取貨",
}
PAYMENT_METHOD_LABELS[PAYMENT_METHOD_NEWEBPAY_GOOGLE_PAY] = "藍新 Google Pay"
PAYMENT_METHOD_LABELS[PAYMENT_METHOD_NEWEBPAY_SAMSUNG_PAY] = "藍新 Samsung Pay"
PAYMENT_STATUS_PENDING = "pending"
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_FAILED = "failed"
PAYMENT_STATUS_LABELS = {
    PAYMENT_STATUS_PENDING: "待付款",
    PAYMENT_STATUS_PAID: "已付款",
    PAYMENT_STATUS_FAILED: "付款失敗",
}

CONVENIENCE_STORE_BRAND_CHOICES = [
    {"value": "UNIMART", "label": "7-ELEVEN"},
    {"value": "FAMI", "label": "全家"},
]
CONVENIENCE_STORE_BRAND_LABELS = {item["value"]: item["label"] for item in CONVENIENCE_STORE_BRAND_CHOICES}


def get_checkout_shipping_methods() -> List[Dict[str, str]]:
    """Return shipping methods currently enabled for buyer checkout."""
    if not LOGISTICS_CHECKOUT_ENABLED:
        return [dict(SHIPPING_METHOD_CHOICES[0])]
    if not LOGISTICS_CHECKOUT_ENABLED:
        return [dict(SHIPPING_METHOD_CHOICES[0])]
    return [dict(item) for item in SHIPPING_METHOD_CHOICES]


def is_checkout_shipping_method_enabled(shipping_method: str) -> bool:
    return shipping_method in {item["value"] for item in get_checkout_shipping_methods()}


def normalize_checkout_shipping_method(shipping_method: str) -> str:
    candidate = (shipping_method or "").strip()
    if is_checkout_shipping_method_enabled(candidate):
        return candidate
    return SHIPPING_METHOD_HOME_DELIVERY


def _shipping_decimal(value: Any, default: str = "0.00") -> Decimal:
    """Normalize shipping config numbers into Decimal."""
    try:
        return Decimal(str(value if value not in (None, "") else default)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal(default).quantize(Decimal("0.01"))


def _format_created_at(value: str) -> str:
    """格式化 訂單 流程中使用的時間或顯示值。

    參數:
        value: 待格式化、待解析或待判斷的值。

    回傳:
        依函式用途回傳對應資料。
    """
    parsed = parse_datetime(value) if value else None
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M") if parsed else ""


def _serialize_totals(totals: Dict[str, Decimal]) -> Dict[str, str]:
    """把 訂單 相關資料整理成較適合輸出或渲染的格式。

    參數:
        totals: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    return {key: format(value, ".2f") for key, value in totals.items()}


def _line_decimal(value: Any) -> Decimal:
    """處理 訂單 相關流程。

    參數:
        value: 待格式化、待解析或待判斷的值。

    回傳:
        數值結果，供後續金額或庫存流程使用。
    """
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _shipping_fee_for_line(product: Dict[str, Any], seller_rules: Dict[str, Any], shipping_method: str) -> Decimal:
    """Resolve the applicable shipping fee for one product line."""
    profile = product_management.prepare_product_for_display(product).get("shipping_profile", {})
    use_seller_rules = bool(profile.get("use_seller_rules", True))

    if shipping_method == SHIPPING_METHOD_HOME_DELIVERY:
        if not use_seller_rules and profile.get("override_home_delivery_fee") is not None:
            return _shipping_decimal(profile.get("override_home_delivery_fee"))
        return _shipping_decimal(seller_rules.get("home_delivery_fee", "80.00"))

    if shipping_method == SHIPPING_METHOD_CONVENIENCE_STORE:
        if not use_seller_rules and profile.get("override_convenience_store_fee") is not None:
            return _shipping_decimal(profile.get("override_convenience_store_fee"))
        return _shipping_decimal(seller_rules.get("convenience_store_fee", "60.00"))

    return Decimal("0.00")


def _available_shipping_methods_for_group(
    lines: List[Dict[str, Any]],
    seller_rules: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Return shipping methods that every product in one seller group supports."""
    if not LOGISTICS_CHECKOUT_ENABLED:
        return [{"value": SHIPPING_METHOD_HOME_DELIVERY, "label": SHIPPING_METHOD_LABELS[SHIPPING_METHOD_HOME_DELIVERY]}]
    available: list[dict[str, str]] = []
    can_use_home = bool(seller_rules.get("home_delivery_enabled", True))
    can_use_store = bool(seller_rules.get("convenience_store_enabled", True))

    for line in lines:
        product = local_store.get_product_by_slug(line["slug"]) or {}
        profile = product_management.prepare_product_for_display(product).get("shipping_profile", {})
        can_use_home = can_use_home and bool(profile.get("allow_home_delivery", True))
        can_use_store = can_use_store and bool(profile.get("allow_convenience_store", True))

    if can_use_home:
        available.append({"value": SHIPPING_METHOD_HOME_DELIVERY, "label": SHIPPING_METHOD_LABELS[SHIPPING_METHOD_HOME_DELIVERY]})
    if can_use_store:
        available.append(
            {"value": SHIPPING_METHOD_CONVENIENCE_STORE, "label": SHIPPING_METHOD_LABELS[SHIPPING_METHOD_CONVENIENCE_STORE]}
        )
    return available


def build_seller_shipping_groups(
    items: List[Dict[str, Any]],
    *,
    shipping_method: str,
) -> List[Dict[str, Any]]:
    """Split cart/order items by seller and calculate shipping per seller."""
    grouped: Dict[str, Dict[str, Any]] = {}
    for raw_line in items:
        line = dict(raw_line)
        if "line_total" not in line:
            line["line_total"] = format(Decimal(str(line["price"])) * int(line["qty"]), ".2f")
        product = local_store.get_product_by_slug(line["slug"]) or {}
        seller_username = str(product.get("owner_username") or line.get("seller_username") or "unknown")
        seller_display_name = str(product.get("owner_display_name") or line.get("seller_display_name") or seller_username)
        bucket = grouped.setdefault(
            seller_username,
            {
                "seller_username": seller_username,
                "seller_display_name": seller_display_name,
                "items": [],
            },
        )
        bucket["items"].append(line)

    groups: List[Dict[str, Any]] = []
    for seller_username, bucket in grouped.items():
        try:
            seller_rules = auth_demo.get_seller_shipping_rules(seller_username)
        except ValueError:
            seller_rules = dict(auth_demo.DEFAULT_SHIPPING_RULES)
        available_shipping_methods = _available_shipping_methods_for_group(bucket["items"], seller_rules)
        available_shipping_values = {item["value"] for item in available_shipping_methods}
        subtotal = sum((_line_decimal(line["line_total"]) for line in bucket["items"]), Decimal("0.00")).quantize(Decimal("0.01"))
        free_shipping_threshold = _shipping_decimal(seller_rules.get("free_shipping_threshold", "1200.00"), "1200.00")

        line_fees = []
        for line in bucket["items"]:
            product = local_store.get_product_by_slug(line["slug"]) or {}
            line_fees.append(_shipping_fee_for_line(product, seller_rules, shipping_method))
        base_shipping_fee = max(line_fees or [Decimal("0.00")]).quantize(Decimal("0.01"))
        free_shipping_applied = subtotal >= free_shipping_threshold if subtotal > 0 else False
        shipping_fee = Decimal("0.00") if free_shipping_applied else base_shipping_fee

        groups.append(
            {
                "seller_username": seller_username,
                "seller_display_name": bucket["seller_display_name"],
                "subtotal": format(subtotal, ".2f"),
                "shipping_fee": format(shipping_fee, ".2f"),
                "base_shipping_fee": format(base_shipping_fee, ".2f"),
                "free_shipping_threshold": format(free_shipping_threshold, ".2f"),
                "free_shipping_applied": free_shipping_applied,
                "selected_shipping_method": shipping_method,
                "selected_shipping_method_label": SHIPPING_METHOD_LABELS.get(shipping_method, shipping_method),
                "available_shipping_methods": available_shipping_methods,
                "selected_shipping_method_supported": shipping_method in available_shipping_values,
                "items": [
                    {
                        "key": line.get("key", ""),
                        "slug": line["slug"],
                        "display_name": line.get("display_name") or line.get("name", ""),
                        "qty": int(line["qty"]),
                        "line_total": format(_line_decimal(line["line_total"]), ".2f"),
                    }
                    for line in bucket["items"]
                ],
            }
        )

    return groups


def build_checkout_totals(
    session,
    *,
    shipping_method: str,
) -> Dict[str, Any]:
    """Build marketplace checkout totals using per-seller shipping groups."""
    shipping_method = normalize_checkout_shipping_method(shipping_method)
    cart = cart_service.get_cart(session)
    items = list(cart.get("items", {}).values())
    subtotal = sum((Decimal(str(item["price"])) * int(item["qty"]) for item in items), Decimal("0.00")).quantize(Decimal("0.01"))
    discount = cart_service.compute_totals(session)["discount"]
    seller_shipping_groups = build_seller_shipping_groups(items, shipping_method=shipping_method)
    unsupported_groups = [group for group in seller_shipping_groups if not group["selected_shipping_method_supported"]]

    shipping = sum((_shipping_decimal(group["shipping_fee"]) for group in seller_shipping_groups), Decimal("0.00")).quantize(Decimal("0.01"))
    total = (subtotal + shipping - discount).quantize(Decimal("0.01"))
    return {
        "totals": {
            "subtotal": subtotal,
            "shipping": shipping,
            "discount": discount,
            "total": total,
        },
        "seller_shipping_groups": seller_shipping_groups,
        "unsupported_sellers": [group["seller_display_name"] for group in unsupported_groups],
    }


def _parse_order_date(value: str) -> date | None:
    """解析原始輸入值，轉成 訂單 流程內部使用的格式。

    參數:
        value: 待格式化、待解析或待判斷的值。

    回傳:
        依函式用途回傳對應資料。
    """
    parsed = parse_datetime(value) if value else None
    if not parsed:
        return None
    return timezone.localtime(parsed).date()


def _normalize_date_filters(date_from: str = "", date_to: str = "") -> Dict[str, Any]:
    """正規化輸入資料，降低 訂單 流程中的格式差異。

    參數:
        date_from: 查詢區間起日，格式通常為 YYYY-MM-DD。
        date_to: 查詢區間迄日，格式通常為 YYYY-MM-DD。

    回傳:
        依函式用途回傳對應資料。
    """
    return {
        "date_from": date_from.strip(),
        "date_to": date_to.strip(),
        "date_from_value": parse_date(date_from.strip()) if date_from.strip() else None,
        "date_to_value": parse_date(date_to.strip()) if date_to.strip() else None,
    }


def _matches_date_filter(order: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    """判斷 訂單 條件是否成立。

    參數:
        order: 函式執行所需的輸入資料。
        filters: 已整理好的篩選條件集合。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    order_date = _parse_order_date(order.get("created_at", ""))
    if not order_date:
        return True
    if filters.get("date_from_value") and order_date < filters["date_from_value"]:
        return False
    if filters.get("date_to_value") and order_date > filters["date_to_value"]:
        return False
    return True


def _empty_service_request() -> Dict[str, str]:
    """處理 訂單 相關流程。

    回傳:
        依函式用途回傳對應資料。
    """
    return {
        "type": "",
        "status": "",
        "reason": "",
        "note": "",
        "created_at": "",
        "reviewed_at": "",
    }


def _enrich_service_request(service_request: Dict[str, Any] | None) -> Dict[str, Any]:
    """處理 訂單 相關流程。

    參數:
        service_request: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    request = dict(service_request or _empty_service_request())
    request.setdefault("type", "")
    request.setdefault("status", "")
    request.setdefault("reason", "")
    request.setdefault("note", "")
    request.setdefault("created_at", "")
    request.setdefault("reviewed_at", "")
    request["type_label"] = SERVICE_REQUEST_TYPE_LABELS.get(request["type"], "")
    request["status_label"] = SERVICE_REQUEST_STATUS_LABELS.get(request["status"], "")
    request["created_at_display"] = _format_created_at(request["created_at"])
    request["reviewed_at_display"] = _format_created_at(request["reviewed_at"])
    request["is_pending"] = request["status"] == SERVICE_REQUEST_PENDING
    return request


def _enrich_seller_line(line: Dict[str, Any]) -> Dict[str, Any]:
    """處理 訂單 相關流程。

    參數:
        line: 單一訂單行或購物車行資料。

    回傳:
        依函式用途回傳對應資料。
    """
    item = dict(line)
    if not item.get("seller_user_id") and item.get("seller_username"):
        seller = local_store.get_user_by_username(str(item["seller_username"]))
        if seller:
            item["seller_user_id"] = seller["id"]
    item["display_name"] = item.get("display_name") or (
        f"{item.get('name', '')} - {item.get('variant_name', '')}" if item.get("variant_name") else item.get("name", "")
    )
    item["seller_status"] = item.get("seller_status", SELLER_STATUS_PENDING)
    item["seller_status_label"] = SELLER_STATUS_LABELS.get(item["seller_status"], item["seller_status"])
    item["shipping_note"] = item.get("shipping_note", "")
    item["tracking_number"] = item.get("tracking_number", "")
    item["shipped_at_display"] = _format_created_at(item.get("shipped_at", ""))
    item["completed_at_display"] = _format_created_at(item.get("completed_at", ""))
    return item


def _derive_seller_status(seller_items: List[Dict[str, Any]]) -> str:
    """根據現有資料推導 訂單 流程需要的狀態值。

    參數:
        seller_items: 屬於同一賣家的訂單品項集合。

    回傳:
        依函式用途回傳對應資料。
    """
    statuses = {line.get("seller_status", SELLER_STATUS_PENDING) for line in seller_items}
    if statuses == {SELLER_STATUS_COMPLETED}:
        return SELLER_STATUS_COMPLETED
    if SELLER_STATUS_SHIPPED in statuses or SELLER_STATUS_COMPLETED in statuses:
        return SELLER_STATUS_SHIPPED
    return SELLER_STATUS_PENDING


def _build_buyer_shipment_groups(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """建立 訂單 流程需要的中繼資料或檢視模型。

    參數:
        items: 訂單或購物車中的品項列表。

    回傳:
        依函式用途回傳對應資料。
    """
    grouped: Dict[str, Dict[str, Any]] = {}
    for raw_line in items:
        line = _enrich_seller_line(raw_line)
        seller_username = line.get("seller_username") or "unknown"
        bucket = grouped.setdefault(
            seller_username,
            {
                "seller_username": seller_username,
                "seller_display_name": line.get("seller_display_name") or "Unknown Seller",
                "items": [],
            },
        )
        bucket["items"].append(line)

    results = []
    for bucket in grouped.values():
        seller_status = _derive_seller_status(bucket["items"])
        first_line = bucket["items"][0]
        results.append(
            {
                "seller_username": bucket["seller_username"],
                "seller_display_name": bucket["seller_display_name"],
                "seller_status": seller_status,
                "seller_status_label": SELLER_STATUS_LABELS.get(seller_status, seller_status),
                "tracking_number": first_line.get("tracking_number", ""),
                "shipping_note": first_line.get("shipping_note", ""),
                "shipped_at_display": first_line.get("shipped_at_display", ""),
                "completed_at_display": first_line.get("completed_at_display", ""),
                "items": bucket["items"],
            }
        )
    return results


def _all_items_pending(items: List[Dict[str, Any]]) -> bool:
    """判斷 訂單 條件是否成立。

    參數:
        items: 訂單或購物車中的品項列表。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return all(_enrich_seller_line(item)["seller_status"] == SELLER_STATUS_PENDING for item in items)


def _any_item_shipped(items: List[Dict[str, Any]]) -> bool:
    """判斷 訂單 條件是否成立。

    參數:
        items: 訂單或購物車中的品項列表。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return any(_enrich_seller_line(item)["seller_status"] in {SELLER_STATUS_SHIPPED, SELLER_STATUS_COMPLETED} for item in items)


def _all_items_shipped_or_completed(items: List[Dict[str, Any]]) -> bool:
    """Return whether every line has reached shipped-or-completed state."""
    if not items:
        return False
    return all(
        _enrich_seller_line(item)["seller_status"] in {SELLER_STATUS_SHIPPED, SELLER_STATUS_COMPLETED}
        for item in items
    )


def _all_items_completed(items: List[Dict[str, Any]]) -> bool:
    """Return whether every line is already completed."""
    if not items:
        return False
    return all(_enrich_seller_line(item)["seller_status"] == SELLER_STATUS_COMPLETED for item in items)


def _can_request_cancel(order: Dict[str, Any]) -> bool:
    """處理 訂單 相關流程。

    參數:
        order: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    service_request = _enrich_service_request(order.get("service_request"))
    if service_request["is_pending"]:
        return False
    if order.get("status", ORDER_STATUS_CONFIRMED) != ORDER_STATUS_CONFIRMED:
        return False
    return _all_items_pending(order.get("items", []))


def _can_request_refund(order: Dict[str, Any]) -> bool:
    """處理 訂單 相關流程。

    參數:
        order: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    service_request = _enrich_service_request(order.get("service_request"))
    if service_request["is_pending"]:
        return False
    if order.get("status", ORDER_STATUS_CONFIRMED) != ORDER_STATUS_CONFIRMED:
        return False
    return _any_item_shipped(order.get("items", []))


def _can_confirm_completion(order: Dict[str, Any]) -> bool:
    """Return whether the buyer can confirm the order as completed."""
    service_request = _enrich_service_request(order.get("service_request"))
    if service_request["is_pending"]:
        return False
    if order.get("status", ORDER_STATUS_CONFIRMED) != ORDER_STATUS_CONFIRMED:
        return False
    items = order.get("items", [])
    if not _all_items_shipped_or_completed(items):
        return False
    return not _all_items_completed(items)


def _enrich_order_common(order: Dict[str, Any]) -> Dict[str, Any]:
    """處理 訂單 相關流程。

    參數:
        order: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    item = dict(order)
    if not item.get("buyer_user_id") and item.get("username"):
        buyer = local_store.get_user_by_username(str(item["username"]))
        if buyer:
            item["buyer_user_id"] = buyer["id"]
    item["created_at_display"] = _format_created_at(item.get("created_at", ""))
    item["item_count"] = sum(line["qty"] for line in item.get("items", []))
    item["status"] = item.get("status", ORDER_STATUS_CONFIRMED)
    item["status_label"] = ORDER_STATUS_LABELS.get(item["status"], item["status"])
    item["service_request"] = _enrich_service_request(item.get("service_request"))
    item["can_request_cancel"] = _can_request_cancel(item)
    item["can_request_refund"] = _can_request_refund(item)
    item["can_confirm_completion"] = _can_confirm_completion(item)
    item["buyer_note"] = item.get("buyer_note", "")
    shipping_address = item.get("shipping_address") or {}
    item["shipping_address"] = dict(shipping_address) if isinstance(shipping_address, dict) else {}
    invoice_profile = item.get("invoice_profile") or {}
    item["invoice_profile"] = dict(invoice_profile) if isinstance(invoice_profile, dict) else {}
    item["shipping_method"] = item.get("shipping_method", SHIPPING_METHOD_HOME_DELIVERY)
    item["shipping_method_label"] = SHIPPING_METHOD_LABELS.get(item["shipping_method"], item["shipping_method"])
    item["payment_method"] = item.get("payment_method", PAYMENT_METHOD_NEWEBPAY)
    item["payment_method_label"] = PAYMENT_METHOD_LABELS.get(item["payment_method"], item["payment_method"])
    item["payment_status"] = item.get("payment_status", PAYMENT_STATUS_PENDING)
    item["payment_status_label"] = PAYMENT_STATUS_LABELS.get(item["payment_status"], item["payment_status"])
    item["payment_trade_no"] = item.get("payment_trade_no", "")
    item["payment_completed_at"] = item.get("payment_completed_at", "")
    item["is_convenience_store_shipping"] = item["shipping_method"] == SHIPPING_METHOD_CONVENIENCE_STORE
    item["pickup_store_brand"] = item.get("pickup_store_brand", "")
    item["pickup_store_brand_label"] = CONVENIENCE_STORE_BRAND_LABELS.get(item["pickup_store_brand"], item["pickup_store_brand"])
    item["pickup_store_code"] = item.get("pickup_store_code", "")
    item["pickup_store_name"] = item.get("pickup_store_name", "")
    item["pickup_store_address"] = item.get("pickup_store_address", "")
    item["seller_shipping_groups"] = item.get("seller_shipping_groups") or build_seller_shipping_groups(
        item.get("items", []),
        shipping_method=item["shipping_method"],
    )
    return item


def create_order_from_cart(
    session,
    user: Dict[str, str],
    *,
    address_id: int | None = None,
    shipping_method: str = SHIPPING_METHOD_HOME_DELIVERY,
    pickup_store_brand: str = "",
    pickup_store_code: str = "",
    pickup_store_name: str = "",
    pickup_store_address: str = "",
    payment_method: str = PAYMENT_METHOD_NEWEBPAY,
    buyer_note: str = "",
) -> Dict[str, Any]:
    """把購物車內容轉成正式訂單，並清空已結帳品項。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。
        user: 目前操作中的會員快照資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    cart = cart_service.get_cart(session)
    items = list(cart.get("items", {}).values())
    if not items:
        raise ValueError("Your cart is empty.")

    shipping_method = normalize_checkout_shipping_method(shipping_method)
    if not is_checkout_shipping_method_enabled(shipping_method):
        raise ValueError("Invalid shipping method.")
    if payment_method not in PAYMENT_METHOD_LABELS:
        raise ValueError("Invalid payment method.")

    selected_address = (
        customer_center.get_address_by_id(user["username"], address_id)
        if address_id is not None
        else customer_center.get_default_address(user["username"])
    )
    if not selected_address:
        raise ValueError("Please select a shipping address.")

    checkout_pricing = build_checkout_totals(session, shipping_method=shipping_method)
    if checkout_pricing["unsupported_sellers"]:
        raise ValueError(
            "The selected shipping method is not available for: "
            + ", ".join(checkout_pricing["unsupported_sellers"])
            + "."
        )
    product_management.reserve_stock(items)
    totals = checkout_pricing["totals"]
    orders = local_store.get_orders()
    next_id = max((order["id"] for order in orders), default=0) + 1
    user_record = local_store.get_user_by_username(user["username"]) or {}

    order = {
        "id": next_id,
        "buyer_user_id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "status": ORDER_STATUS_CONFIRMED,
        "coupon": cart.get("coupon"),
        "shipping_address": selected_address,
        "shipping_method": shipping_method,
        "pickup_store_brand": pickup_store_brand.strip(),
        "pickup_store_code": pickup_store_code.strip(),
        "pickup_store_name": pickup_store_name.strip(),
        "pickup_store_address": pickup_store_address.strip(),
        "payment_method": payment_method,
        "payment_status": PAYMENT_STATUS_PENDING,
        "payment_status_label": PAYMENT_STATUS_LABELS[PAYMENT_STATUS_PENDING],
        "payment_trade_no": "",
        "payment_completed_at": "",
        "invoice_profile": customer_center.get_invoice_profile(user["username"]),
        "service_request": _empty_service_request(),
        "buyer_note": buyer_note.strip(),
        "seller_shipping_groups": checkout_pricing["seller_shipping_groups"],
        "items": [
            {
                "id": item["id"],
                "slug": item["slug"],
                "name": item["name"],
                "display_name": item.get("display_name", item["name"]),
                "price": item["price"],
                "qty": item["qty"],
                "variant_id": item.get("variant_id", ""),
                "variant_name": item.get("variant_name", ""),
                "sku": item.get("sku", ""),
                "line_total": format(item["price"] * item["qty"], ".2f"),
                "seller_user_id": (local_store.get_product_by_slug(item["slug"]) or {}).get("owner_user_id"),
                "seller_username": (local_store.get_product_by_slug(item["slug"]) or {}).get("owner_username", ""),
                "seller_display_name": (local_store.get_product_by_slug(item["slug"]) or {}).get("owner_display_name", ""),
                "seller_status": SELLER_STATUS_PENDING,
                "shipping_note": "",
                "tracking_number": "",
                "shipped_at": "",
                "completed_at": "",
            }
            for item in items
        ],
        "totals": _serialize_totals(totals),
        "created_at": timezone.localtime().isoformat(),
        "buyer_email": user_record.get("email", ""),
    }
    orders.append(order)
    local_store.save_orders(orders)
    cart_service.clear(session)
    return order


def list_orders_for_user(username: str) -> List[Dict[str, Any]]:
    """列出 訂單 相關資料，供頁面或 API 顯示。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    results = []
    for order in local_store.get_orders_by_username(username):
        item = _enrich_order_common(order)
        shipment_groups = _build_buyer_shipment_groups(item.get("items", []))
        item["shipment_groups"] = shipment_groups
        item["shipment_summary"] = " / ".join(group["seller_status_label"] for group in shipment_groups) or "待出貨"
        results.append(item)
    return results


def get_checkout_shipping_methods() -> List[Dict[str, str]]:
    """回傳 checkout 可選的物流方式。"""
    return [dict(item) for item in SHIPPING_METHOD_CHOICES]


def get_checkout_payment_methods() -> List[Dict[str, str]]:
    """回傳 checkout 可選的付款方式。"""
    return [dict(item) for item in PAYMENT_METHOD_CHOICES]


def get_convenience_store_brands() -> List[Dict[str, str]]:
    """回傳 checkout 可選的超商品牌。"""
    if not LOGISTICS_CHECKOUT_ENABLED:
        return []
    return [dict(item) for item in CONVENIENCE_STORE_BRAND_CHOICES]


def get_order_detail_for_user(order_id: int, username: str) -> Optional[Dict[str, Any]]:
    """取得 訂單 流程中指定條件的資料。

    參數:
        order_id: 訂單編號。
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    order = local_store.get_order_by_id(order_id)
    if not order or order.get("username") != username:
        return None
    item = _enrich_order_common(order)
    item["items"] = [_enrich_seller_line(line) for line in item.get("items", [])]
    item["shipment_groups"] = _build_buyer_shipment_groups(item["items"])
    return item


def request_order_service(order_id: int, username: str, *, request_type: str, reason: str) -> Dict[str, Any]:
    """建立買家的取消或退款申請。

    參數:
        order_id: 訂單編號。
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        request_type: 售後申請類型，例如 cancel 或 refund。
        reason: 使用者提交的原因說明。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    clean_reason = reason.strip()
    if not clean_reason:
        raise ValueError("Please provide a reason.")
    if request_type not in {SERVICE_REQUEST_CANCEL, SERVICE_REQUEST_REFUND}:
        raise ValueError("Invalid service request type.")

    orders = list(local_store.get_orders())
    for order in orders:
        if order.get("id") != order_id or order.get("username") != username:
            continue
        if request_type == SERVICE_REQUEST_CANCEL and not _can_request_cancel(order):
            raise ValueError("This order can no longer be cancelled.")
        if request_type == SERVICE_REQUEST_REFUND and not _can_request_refund(order):
            raise ValueError("This order is not eligible for refund request yet.")
        order["service_request"] = {
            "type": request_type,
            "status": SERVICE_REQUEST_PENDING,
            "reason": clean_reason,
            "note": "",
            "created_at": timezone.localtime().isoformat(),
            "reviewed_at": "",
        }
        local_store.save_orders(orders)
        refreshed = local_store.get_order_by_id(order_id) or order
        return _enrich_order_common(refreshed)
    raise ValueError("Order not found.")


def confirm_order_completion(order_id: int, username: str) -> Dict[str, Any]:
    """Allow the buyer to confirm receipt and complete the order."""
    orders = list(local_store.get_orders())
    for order in orders:
        if order.get("id") != order_id or order.get("username") != username:
            continue
        if not _can_confirm_completion(order):
            raise ValueError("This order is not ready for buyer completion yet.")
        completed_at = timezone.localtime().isoformat()
        for line in order.get("items", []):
            if line.get("seller_status") in {SELLER_STATUS_SHIPPED, SELLER_STATUS_COMPLETED}:
                if not line.get("shipped_at"):
                    line["shipped_at"] = completed_at
                line["seller_status"] = SELLER_STATUS_COMPLETED
                line["completed_at"] = completed_at
        local_store.save_orders(orders)
        refreshed = local_store.get_order_by_id(order_id) or order
        item = _enrich_order_common(refreshed)
        item["items"] = [_enrich_seller_line(line) for line in item.get("items", [])]
        item["shipment_groups"] = _build_buyer_shipment_groups(item["items"])
        return item
    raise ValueError("Order not found.")


def apply_newebpay_result(
    order_id: int,
    *,
    payment_method: str,
    payment_status: str,
    trade_no: str = "",
    paid_at: str = "",
    pickup_store_brand: str = "",
    pickup_store_code: str = "",
    pickup_store_name: str = "",
    pickup_store_address: str = "",
) -> Dict[str, Any] | None:
    """Persist NewebPay callback data back onto the stored order."""
    orders = list(local_store.get_orders())
    for order in orders:
        if order.get("id") != order_id:
            continue
        clean_payment_method = payment_method.strip() or order.get("payment_method", PAYMENT_METHOD_NEWEBPAY)
        clean_payment_status = payment_status.strip() or order.get("payment_status", PAYMENT_STATUS_PENDING)
        order["payment_method"] = clean_payment_method
        order["payment_status"] = clean_payment_status
        order["payment_status_label"] = PAYMENT_STATUS_LABELS.get(clean_payment_status, clean_payment_status)
        if trade_no.strip():
            order["payment_trade_no"] = trade_no.strip()
        if paid_at.strip():
            order["payment_completed_at"] = paid_at.strip()

        has_store_selection = bool(pickup_store_code.strip() and pickup_store_name.strip())
        if has_store_selection:
            order["shipping_method"] = SHIPPING_METHOD_CONVENIENCE_STORE
            order["pickup_store_brand"] = pickup_store_brand.strip()
            order["pickup_store_code"] = pickup_store_code.strip()
            order["pickup_store_name"] = pickup_store_name.strip()
            order["pickup_store_address"] = pickup_store_address.strip()
        elif order.get("shipping_method") != SHIPPING_METHOD_CONVENIENCE_STORE:
            order["pickup_store_brand"] = ""
            order["pickup_store_code"] = ""
            order["pickup_store_name"] = ""
            order["pickup_store_address"] = ""

        local_store.save_orders(orders)
        refreshed = local_store.get_order_by_id(order_id) or order
        return _enrich_order_common(refreshed)
    return None


def _build_seller_order_view(order: Dict[str, Any], seller_username: str) -> Optional[Dict[str, Any]]:
    """建立 訂單 流程需要的中繼資料或檢視模型。

    參數:
        order: 函式執行所需的輸入資料。
        seller_username: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    seller_items = [_enrich_seller_line(line) for line in order.get("items", []) if line.get("seller_username") == seller_username]
    if not seller_items:
        return None

    seller_subtotal = sum((_line_decimal(line.get("line_total", "0")) for line in seller_items), Decimal("0.00"))
    seller_status = _derive_seller_status(seller_items)
    item = _enrich_order_common(order)
    item["items"] = seller_items
    item["seller_status"] = seller_status
    item["seller_status_label"] = SELLER_STATUS_LABELS.get(seller_status, seller_status)
    item["shipping_note"] = seller_items[0].get("shipping_note", "")
    item["tracking_number"] = seller_items[0].get("tracking_number", "")
    item["shipped_at_display"] = seller_items[0].get("shipped_at_display", "")
    item["completed_at_display"] = seller_items[0].get("completed_at_display", "")
    item["seller_totals"] = {"subtotal": format(seller_subtotal, ".2f")}
    return item


def list_orders_for_seller(username: str, *, date_from: str = "", date_to: str = "") -> List[Dict[str, Any]]:
    """列出 訂單 相關資料，供頁面或 API 顯示。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        date_from: 查詢區間起日，格式通常為 YYYY-MM-DD。
        date_to: 查詢區間迄日，格式通常為 YYYY-MM-DD。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    filters = _normalize_date_filters(date_from, date_to)
    items: List[Dict[str, Any]] = []
    for order in sorted(local_store.get_orders(), key=lambda item: item.get("created_at", ""), reverse=True):
        if not _matches_date_filter(order, filters):
            continue
        seller_order = _build_seller_order_view(order, username)
        if seller_order:
            items.append(seller_order)
    return items


def get_order_detail_for_seller(order_id: int, username: str) -> Optional[Dict[str, Any]]:
    """取得 訂單 流程中指定條件的資料。

    參數:
        order_id: 訂單編號。
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    order = local_store.get_order_by_id(order_id)
    if not order:
        return None
    return _build_seller_order_view(order, username)


def update_seller_order(
    order_id: int,
    seller_username: str,
    *,
    seller_status: str,
    shipping_note: str = "",
    tracking_number: str = "",
) -> Dict[str, Any]:
    """更新賣家履約狀態、物流編號與出貨備註。

    參數:
        order_id: 訂單編號。
        seller_username: 函式執行所需的輸入資料。
        seller_status: 函式執行所需的輸入資料。
        shipping_note: 函式執行所需的輸入資料。
        tracking_number: 函式執行所需的輸入資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    if seller_status not in SELLER_STATUS_LABELS:
        raise ValueError("Invalid seller order status.")

    orders = list(local_store.get_orders())
    for order in orders:
        if order.get("id") != order_id:
            continue
        if order.get("status") != ORDER_STATUS_CONFIRMED:
            raise ValueError("This order is no longer editable.")
        matched = False
        for line in order.get("items", []):
            if line.get("seller_username") != seller_username:
                continue
            matched = True
            line["seller_status"] = seller_status
            line["shipping_note"] = shipping_note.strip()
            line["tracking_number"] = tracking_number.strip()
            if seller_status == SELLER_STATUS_SHIPPED and not line.get("shipped_at"):
                line["shipped_at"] = timezone.localtime().isoformat()
            if seller_status == SELLER_STATUS_COMPLETED:
                if not line.get("shipped_at"):
                    line["shipped_at"] = timezone.localtime().isoformat()
                line["completed_at"] = timezone.localtime().isoformat()
            if seller_status == SELLER_STATUS_PENDING:
                line["completed_at"] = ""
        if not matched:
            raise ValueError("Order not found.")
        local_store.save_orders(orders)
        refreshed = local_store.get_order_by_id(order_id)
        return _build_seller_order_view(refreshed or order, seller_username) or {}
    raise ValueError("Order not found.")


def build_sales_report(username: str, *, date_from: str = "", date_to: str = "") -> Dict[str, Any]:
    """依賣家與日期區間彙整銷售報表資料。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        date_from: 查詢區間起日，格式通常為 YYYY-MM-DD。
        date_to: 查詢區間迄日，格式通常為 YYYY-MM-DD。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    orders = list_orders_for_seller(username, date_from=date_from, date_to=date_to)
    total_revenue = Decimal("0.00")
    total_units = 0
    status_counts = {
        SELLER_STATUS_PENDING: 0,
        SELLER_STATUS_SHIPPED: 0,
        SELLER_STATUS_COMPLETED: 0,
    }
    product_sales: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"name": "", "qty": 0, "revenue": Decimal("0.00")})

    for order in orders:
        if order["status"] != ORDER_STATUS_CONFIRMED:
            continue
        total_revenue += _line_decimal(order["seller_totals"]["subtotal"])
        total_units += order["item_count"]
        status_counts[order["seller_status"]] = status_counts.get(order["seller_status"], 0) + 1
        for line in order.get("items", []):
            bucket = product_sales[line["slug"]]
            bucket["name"] = line["name"]
            bucket["qty"] += int(line["qty"])
            bucket["revenue"] += _line_decimal(line["line_total"])

    top_products = sorted(
        [
            {
                "slug": slug,
                "name": item["name"],
                "qty": item["qty"],
                "revenue": format(item["revenue"], ".2f"),
            }
            for slug, item in product_sales.items()
        ],
        key=lambda item: (item["qty"], Decimal(item["revenue"])),
        reverse=True,
    )

    return {
        "order_count": len([item for item in orders if item["status"] == ORDER_STATUS_CONFIRMED]),
        "units_sold": total_units,
        "revenue": format(total_revenue, ".2f"),
        "status_counts": {
            "pending": status_counts[SELLER_STATUS_PENDING],
            "shipped": status_counts[SELLER_STATUS_SHIPPED],
            "completed": status_counts[SELLER_STATUS_COMPLETED],
        },
        "top_products": top_products[:5],
        "filters": {"date_from": date_from, "date_to": date_to},
    }


def _build_admin_order_view(order: Dict[str, Any]) -> Dict[str, Any]:
    """建立 訂單 流程需要的中繼資料或檢視模型。

    參數:
        order: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    item = _enrich_order_common(order)
    item["items"] = [_enrich_seller_line(line) for line in item.get("items", [])]
    item["shipment_groups"] = _build_buyer_shipment_groups(item["items"])
    item["seller_count"] = len(item["shipment_groups"])
    return item


def list_orders_for_admin(
    *,
    date_from: str = "",
    date_to: str = "",
    status: str = "",
    service_status: str = "",
    q: str = "",
) -> List[Dict[str, Any]]:
    """列出 訂單 相關資料，供頁面或 API 顯示。

    參數:
        date_from: 查詢區間起日，格式通常為 YYYY-MM-DD。
        date_to: 查詢區間迄日，格式通常為 YYYY-MM-DD。
        status: 函式執行所需的輸入資料。
        service_status: 函式執行所需的輸入資料。
        q: 函式執行所需的輸入資料。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    filters = _normalize_date_filters(date_from, date_to)
    status_value = status.strip().lower()
    service_status_value = service_status.strip().lower()
    search_value = q.strip().lower()
    orders = []
    for order in sorted(local_store.get_orders(), key=lambda item: item.get("created_at", ""), reverse=True):
        if not _matches_date_filter(order, filters):
            continue
        view = _build_admin_order_view(order)
        if status_value and view["status"] != status_value:
            continue
        if service_status_value and view["service_request"]["status"] != service_status_value:
            continue
        if search_value and search_value not in str(view.get("username", "")).lower() and search_value not in str(view.get("display_name", "")).lower() and search_value not in str(view.get("id", "")).lower():
            continue
        orders.append(view)
    return orders


def get_order_detail_for_admin(order_id: int) -> Optional[Dict[str, Any]]:
    """取得 訂單 流程中指定條件的資料。

    參數:
        order_id: 訂單編號。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    order = local_store.get_order_by_id(order_id)
    if not order:
        return None
    return _build_admin_order_view(order)


def review_service_request(order_id: int, *, approved: bool, note: str = "") -> Dict[str, Any]:
    """由管理員審核買家的售後申請。

    參數:
        order_id: 訂單編號。
        approved: 是否核准此次審核或申請。
        note: 補充說明、審核備註或操作備註。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    orders = list(local_store.get_orders())
    for order in orders:
        if order.get("id") != order_id:
            continue
        request = _enrich_service_request(order.get("service_request"))
        if not request["is_pending"]:
            raise ValueError("This order has no pending service request.")

        order.setdefault("service_request", {})
        order["service_request"]["status"] = SERVICE_REQUEST_APPROVED if approved else SERVICE_REQUEST_REJECTED
        order["service_request"]["note"] = note.strip()
        order["service_request"]["reviewed_at"] = timezone.localtime().isoformat()

        if approved and request["type"] == SERVICE_REQUEST_CANCEL:
            order["status"] = ORDER_STATUS_CANCELLED
            product_management.restock_items(order.get("items", []))
        elif approved and request["type"] == SERVICE_REQUEST_REFUND:
            order["status"] = ORDER_STATUS_REFUNDED

        local_store.save_orders(orders)
        refreshed = local_store.get_order_by_id(order_id) or order
        return _build_admin_order_view(refreshed)
    raise ValueError("Order not found.")


def build_admin_order_summary() -> Dict[str, Any]:
    """彙整平台管理端的訂單摘要統計。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    orders = [_build_admin_order_view(order) for order in local_store.get_orders()]
    pending_requests = [order for order in orders if order["service_request"]["status"] == SERVICE_REQUEST_PENDING]
    return {
        "order_count": len(orders),
        "confirmed_count": len([order for order in orders if order["status"] == ORDER_STATUS_CONFIRMED]),
        "cancelled_count": len([order for order in orders if order["status"] == ORDER_STATUS_CANCELLED]),
        "refunded_count": len([order for order in orders if order["status"] == ORDER_STATUS_REFUNDED]),
        "pending_service_requests": len(pending_requests),
        "latest_service_requests": pending_requests[:5],
    }
