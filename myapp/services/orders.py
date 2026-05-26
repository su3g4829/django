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
    shipping_address = item.get("shipping_address") or {}
    item["shipping_address"] = dict(shipping_address) if isinstance(shipping_address, dict) else {}
    invoice_profile = item.get("invoice_profile") or {}
    item["invoice_profile"] = dict(invoice_profile) if isinstance(invoice_profile, dict) else {}
    return item


def create_order_from_cart(session, user: Dict[str, str]) -> Dict[str, Any]:
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

    product_management.reserve_stock(items)
    totals = cart_service.compute_totals(session)
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
        "shipping_address": customer_center.get_default_address(user["username"]),
        "invoice_profile": customer_center.get_invoice_profile(user["username"]),
        "service_request": _empty_service_request(),
        "buyer_note": "",
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
