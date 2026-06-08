"""訂單與售後流程服務模組。

涵蓋建立訂單、買家查詢、賣家履約、售後申請與管理端審核等流程。
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from ..models import AppUser as AppUserModel
from ..models import Order as OrderModel
from ..models import OrderItem as OrderItemModel
from ..models import OrderServiceRequest as OrderServiceRequestModel
from ..models import PaymentSource as PaymentSourceModel
from ..models import PaymentStatus as PaymentStatusModel
from ..models import PaymentTransaction as PaymentTransactionModel
from ..models import Product as ProductModel
from ..models import ServiceRequestStatus as ServiceRequestStatusModel
from ..models import ServiceRequestType as ServiceRequestTypeModel
from ..models import ShipmentEvent as ShipmentEventModel
from ..models import ShipmentEventType as ShipmentEventTypeModel
from ..repositories import local_store
from . import auth_demo
from . import cart as cart_service
from . import customer_center
from . import product_management

logger = logging.getLogger(__name__)

# 這個模組同時負責 checkout、訂單查詢、售後流程，以及 JSON/ORM 過渡期同步。
# 下方常數會被買家、賣家、管理端與金流整合流程重用。

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


def _checkout_item_debug_summary(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build a compact, log-friendly checkout item summary."""
    summary: List[Dict[str, Any]] = []
    for item in items:
        summary.append(
            {
                "slug": str(item.get("slug", "")),
                "qty": int(item.get("qty", 0) or 0),
                "price": str(item.get("price", "")),
                "variant_id": str(item.get("variant_id", "")),
                "variant_name": str(item.get("variant_name", "")),
            }
        )
    return summary


def _log_checkout_checkpoint(stage: str, **extra: Any) -> None:
    """Emit checkout checkpoints so Render logs can pinpoint the failing step."""
    logger.info("Checkout checkpoint: %s", stage, extra={"checkout_stage": stage, **extra})


def _db_orders_enabled() -> bool:
    # 檢查訂單相關 ORM 表是否已可用，用來決定後續要走 ORM 還是 legacy JSON 路徑。
    """確認第一波訂單表已可讀寫。

    這裡只檢查資料表是否存在，不用 `.exists()`，避免空表被誤判成 ORM 不可用。
    """
    try:
        OrderModel.objects.count()
        OrderItemModel.objects.count()
        return True
    except Exception:
        return False


def _ensure_db_user_from_username(
    username: str,
    *,
    display_name: str = "",
    email: str = "",
    role: str = "",
) -> AppUserModel | None:
    # 訂單 ORM 需要 buyer / seller 外鍵，這裡會依 username 確保對應 `AppUser` 存在。
    """依照現有 JSON snapshot 補齊 ORM 使用者。

    訂單同步會需要 buyer / seller FK；這裡採最保守策略：
    - 先找 ORM 既有使用者
    - 沒有再從 local_store 補建最小資料
    """
    clean_username = (username or "").strip()
    if not clean_username or not _db_orders_enabled():
        return None

    user = AppUserModel.objects.filter(username=clean_username).first()
    create_defaults = {
        "email": email or f"{clean_username}@example.com",
        "password_hash": "!",
        "display_name": display_name or clean_username,
        "role": role or "member",
        "account_status": "active",
        "seller_request_status": "none",
    }
    if user is None:
        user = AppUserModel.objects.create(username=clean_username, **create_defaults)
    else:
        dirty = False
        update_defaults = {
            "email": email or f"{clean_username}@example.com",
            "display_name": display_name or clean_username,
            "role": role or "member",
            "account_status": "active",
            "seller_request_status": "none",
        }
        for field, value in update_defaults.items():
            if value and getattr(user, field, "") != value:
                setattr(user, field, value)
                dirty = True
        if dirty:
            user.save(update_fields=[*update_defaults.keys(), "updated_at"])
    return user


def _format_money_str(value: Decimal | str | int | float) -> str:
    # 統一輸出為兩位小數字串，供 API payload 與 JSON snapshot 共用。
    """統一把金額格式化成現有 JSON/API 使用的兩位小數字串。"""
    return format(Decimal(str(value)).quantize(Decimal("0.01")), ".2f")


def _service_request_type_to_model(value: str) -> str:
    # service 層目前用 cancel/refund；ORM schema 需要映射到正式列舉值。
    """把現行 cancel/refund 流程映射到第一波 ORM schema。"""
    if value == SERVICE_REQUEST_REFUND:
        return ServiceRequestTypeModel.REFUND
    return ServiceRequestTypeModel.OTHER


def _service_request_type_from_model(value: str) -> str:
    # 讓 ORM 讀出的售後型別回到目前 API / service 慣用值。
    if value == ServiceRequestTypeModel.REFUND:
        return SERVICE_REQUEST_REFUND
    return SERVICE_REQUEST_CANCEL


def _service_request_status_to_model(value: str) -> str:
    # service 層的 pending/approved/rejected 要映射到 ORM schema 狀態。
    if value == SERVICE_REQUEST_APPROVED:
        return ServiceRequestStatusModel.APPROVED
    if value == SERVICE_REQUEST_REJECTED:
        return ServiceRequestStatusModel.REJECTED
    return ServiceRequestStatusModel.OPEN


def _service_request_status_from_model(value: str) -> str:
    # ORM 狀態回寫到 API payload 時，仍沿用前端已使用的 service 值。
    if value == ServiceRequestStatusModel.APPROVED:
        return SERVICE_REQUEST_APPROVED
    if value == ServiceRequestStatusModel.REJECTED:
        return SERVICE_REQUEST_REJECTED
    return SERVICE_REQUEST_PENDING


def _shipment_event_type_for_line_status(seller_status: str) -> str:
    # 賣家履約狀態會同步驅動物流事件表，這裡集中做映射。
    if seller_status == SELLER_STATUS_COMPLETED:
        return ShipmentEventTypeModel.COMPLETED
    if seller_status == SELLER_STATUS_SHIPPED:
        return ShipmentEventTypeModel.SHIPPED
    return ShipmentEventTypeModel.CREATED


def _order_item_record_from_model(item: OrderItemModel) -> Dict[str, Any]:
    # 把 ORM `OrderItem` 轉成目前 service layer / API 共用的 line payload。
    """把 ORM `OrderItem` 還原成舊版 API 相容結構。"""
    return {
        "id": item.id,
        "slug": item.product_slug_snapshot,
        "name": item.product_name_snapshot,
        "display_name": item.product_display_name_snapshot or item.product_name_snapshot,
        "price": float(item.unit_price),
        "qty": int(item.quantity),
        "variant_id": item.variant_external_id_snapshot,
        "variant_name": item.variant_name_snapshot,
        "sku": item.sku_snapshot,
        "line_total": _format_money_str(item.line_total),
        "seller_user_id": item.seller_id,
        "seller_username": item.seller_username_snapshot,
        "seller_display_name": item.seller_display_name_snapshot,
        "seller_status": item.seller_status,
        "shipping_note": item.shipping_note,
        "tracking_number": item.tracking_number,
        "shipped_at": item.shipped_at.isoformat() if item.shipped_at else "",
        "completed_at": item.completed_at.isoformat() if item.completed_at else "",
    }


def _service_request_record_from_model(order: OrderModel) -> Dict[str, Any]:
    # 同一張訂單可能累積多筆售後紀錄；目前 API 只取最新一筆對外顯示。
    requests = list(order.service_requests.all())
    if not requests:
        return _empty_service_request()
    request = sorted(requests, key=lambda item: item.id, reverse=True)[0]
    return {
        "type": _service_request_type_from_model(request.request_type),
        "status": _service_request_status_from_model(request.status),
        "reason": request.reason,
        "note": request.note,
        "created_at": request.created_at.isoformat() if request.created_at else "",
        "reviewed_at": request.reviewed_at.isoformat() if request.reviewed_at else "",
    }


def _latest_payment_from_order_model(order: OrderModel) -> PaymentTransactionModel | None:
    # 訂單可能有多次付款嘗試，前台與後台通常只關心最新那筆交易。
    payments = list(order.payment_transactions.all())
    if not payments:
        return None
    return sorted(payments, key=lambda item: item.id, reverse=True)[0]


def _order_record_from_model(order: OrderModel) -> Dict[str, Any]:
    # 這是 ORM `Order` -> service payload 的核心轉換點。
    # 買家、賣家、管理端訂單 API 都會先經過這裡。
    """把 ORM `Order` 還原成目前前端與 service 仍使用的訂單格式。"""
    payment = _latest_payment_from_order_model(order)
    items = [_order_item_record_from_model(item) for item in order.items.all()]
    shipping_address = {
        "label": order.shipping_label,
        "recipient": order.shipping_recipient,
        "phone": order.shipping_phone,
        "city": order.shipping_city,
        "district": order.shipping_district,
        "postal_code": order.shipping_postal_code,
        "address_line": order.shipping_address_line,
        "is_default": False,
    }
    invoice_profile = {
        "invoice_type": order.invoice_type,
        "carrier_code": order.invoice_carrier_code,
        "company_name": order.invoice_company_name,
        "tax_id": order.invoice_tax_id,
    }
    payment_method = order.payment_method or (payment.payment_type_code if payment else "")
    payment_status = order.payment_status or (payment.status if payment else PAYMENT_STATUS_PENDING)
    payment_trade_no = order.payment_trade_no or (payment.trade_no if payment else "")
    payment_completed_at = (
        order.paid_at.isoformat()
        if order.paid_at
        else (payment.paid_at.isoformat() if payment and payment.paid_at else "")
    )
    return {
        "id": order.id,
        "order_no": order.order_no,
        "buyer_user_id": order.buyer_id,
        "username": order.buyer_username_snapshot or (order.buyer.username if order.buyer else ""),
        "display_name": order.buyer_display_name_snapshot or (order.buyer.display_name if order.buyer else ""),
        "status": order.status,
        "shipping_method": order.shipping_method,
        "pickup_store_brand": order.pickup_store_type,
        "pickup_store_code": order.pickup_store_code,
        "pickup_store_name": order.pickup_store_name,
        "pickup_store_address": order.pickup_store_address,
        "payment_method": payment_method or PAYMENT_METHOD_NEWEBPAY,
        "payment_status": payment_status or PAYMENT_STATUS_PENDING,
        "payment_status_label": PAYMENT_STATUS_LABELS.get(payment_status or PAYMENT_STATUS_PENDING, payment_status or PAYMENT_STATUS_PENDING),
        "payment_trade_no": payment_trade_no,
        "payment_completed_at": payment_completed_at,
        "invoice_profile": invoice_profile,
        "service_request": _service_request_record_from_model(order),
        "buyer_note": order.note,
        "seller_shipping_groups": build_seller_shipping_groups(items, shipping_method=order.shipping_method),
        "items": items,
        "totals": {
            "subtotal": _format_money_str(order.subtotal_amount),
            "shipping": _format_money_str(order.shipping_amount),
            "discount": _format_money_str(order.discount_amount),
            "total": _format_money_str(order.total_amount),
        },
        "created_at": order.created_at.isoformat() if order.created_at else "",
        "buyer_email": order.buyer_email,
        "shipping_address": shipping_address,
    }


def _merge_order_records(preferred_record: Dict[str, Any], fallback_record: Dict[str, Any] | None = None) -> Dict[str, Any]:
    # ORM 與 JSON 並行期間，盡量以 preferred 為主，但保留 fallback 裡仍有價值的欄位。
    """合併 ORM 與 JSON 訂單資料，保留 JSON 尚未落表的欄位。"""
    merged = deepcopy(fallback_record or {})
    preferred = deepcopy(preferred_record)
    for key, value in preferred.items():
        if key in {"shipping_address", "invoice_profile", "service_request"}:
            fallback_value = merged.get(key) if isinstance(merged.get(key), dict) else {}
            preferred_value = value if isinstance(value, dict) else {}
            merged[key] = {**fallback_value, **preferred_value}
            continue
        if value in (None, "", [], {}) and key in merged:
            continue
        merged[key] = value
    return merged


def _db_orders_queryset():
    # 共用 queryset：集中處理 select_related / prefetch_related，避免下游重複寫。
    return (
        OrderModel.objects.select_related("buyer")
        .prefetch_related("items__seller", "service_requests", "payment_transactions")
        .order_by("-id")
    )


def _json_order_by_id(order_id: int) -> Dict[str, Any] | None:
    """Return one legacy JSON order payload by id when it still exists locally."""
    return next((deepcopy(item) for item in local_store.get_orders() if int(item.get("id") or 0) == order_id), None)


def _db_order_record_by_id(order_id: int) -> Dict[str, Any] | None:
    """Serialize one ORM order into the legacy service payload shape."""
    if not _db_orders_enabled():
        return None
    order = _db_orders_queryset().filter(id=order_id).first()
    if order is None:
        return None
    return _order_record_from_model(order)


def _merged_order_record_by_id(order_id: int) -> Dict[str, Any] | None:
    """Return one order payload with ORM preferred and JSON-only fields preserved."""
    orm_record = _db_order_record_by_id(order_id)
    if _db_orders_enabled():
        return orm_record
    json_record = _json_order_by_id(order_id)
    if orm_record and json_record:
        return _merge_order_records(orm_record, json_record)
    return orm_record or json_record


def _save_order_record_to_json(order_record: Dict[str, Any]) -> Dict[str, Any]:
    """Persist one legacy order payload back into `orders.json` for compatibility."""
    orders = list(local_store.get_orders())
    order_id = int(order_record.get("id") or 0)
    existing = next((deepcopy(item) for item in orders if int(item.get("id") or 0) == order_id), None)
    merged = _merge_order_records(order_record, existing)

    replaced = False
    for index, item in enumerate(orders):
        if int(item.get("id") or 0) != order_id:
            continue
        orders[index] = merged
        replaced = True
        break
    if not replaced:
        orders.append(merged)
    local_store.save_orders(orders)
    return merged


def _persist_order_record(order_record: Dict[str, Any]) -> Dict[str, Any]:
    """Write one order through ORM first, then sync the canonical payload back to JSON."""
    order_model = _sync_order_record_to_orm(order_record)
    if order_model is not None:
        canonical = _merge_order_records(_order_record_from_model(order_model), order_record)
    else:
        canonical = deepcopy(order_record)
    if _db_orders_enabled():
        return canonical
    return _save_order_record_to_json(canonical)


def _merged_order_records() -> List[Dict[str, Any]]:
    # 取得目前可用的完整訂單清單；ORM 啟用後優先走 ORM，否則退回 JSON。
    """回傳 ORM 優先、JSON fallback 的訂單清單。"""
    if _db_orders_enabled():
        records = [_order_record_from_model(order) for order in _db_orders_queryset()]
        return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)
    json_records = {int(order.get("id", 0)): deepcopy(order) for order in local_store.get_orders() if order.get("id")}
    return list(json_records.values())


def _sync_payment_record_to_orm(order_model: OrderModel, order_record: Dict[str, Any]) -> None:
    # 把訂單摘要中的付款欄位同步到 `payment_transactions`，方便 staff debug 與後續 query。
    """把訂單上的付款摘要同步到 payment_transactions。"""
    merchant_order_no = (order_record.get("payment_merchant_order_no") or order_model.payment_merchant_order_no or "").strip()
    trade_no = (order_record.get("payment_trade_no") or "").strip()
    if not merchant_order_no and not trade_no:
        return

    defaults = {
        "provider": "newebpay",
        "source": PaymentSourceModel.MANUAL,
        "status": order_record.get("payment_status") or PaymentStatusModel.PENDING,
        "amount": Decimal(str(order_record.get("totals", {}).get("total", order_model.total_amount or "0"))),
        "merchant_id": "",
        "merchant_order_no": merchant_order_no or order_model.payment_merchant_order_no or f"ORDER{order_model.id}",
        "trade_no": trade_no,
        "payment_type_code": order_record.get("payment_method", order_model.payment_method or ""),
        "payment_method_label": PAYMENT_METHOD_LABELS.get(order_record.get("payment_method", ""), order_record.get("payment_method", "")),
        "paid_at": parse_datetime(order_record.get("payment_completed_at", "")) if order_record.get("payment_completed_at") else None,
    }
    PaymentTransactionModel.objects.update_or_create(
        order=order_model,
        merchant_order_no=defaults["merchant_order_no"],
        defaults=defaults,
    )


def _sync_order_record_to_orm(order_record: Dict[str, Any]) -> OrderModel | None:
    # 讓既有 JSON 形狀的訂單資料可以回寫到 ORM。
    # 同步時會保留 `Order.id`，並依 payload 重建 `OrderItem` 與相關摘要欄位。
    """把單筆 JSON 訂單同步到 ORM。

    第一階段仍以 JSON 為主，因此這裡採最直接可靠的方式：
    - `Order` 以 JSON `id` 對齊 ORM 主鍵
    - `OrderItem` 每次同步先刪後建，避免舊 snapshot 殘留
    """
    if not _db_orders_enabled():
        return None

    order_id = int(order_record.get("id") or 0)
    if order_id <= 0:
        return None

    shipping_address = order_record.get("shipping_address") or {}
    invoice_profile = order_record.get("invoice_profile") or {}
    buyer_username = str(order_record.get("username", "")).strip()
    buyer = (
        _ensure_db_user_from_username(
            buyer_username,
            display_name=str(order_record.get("display_name", "")),
            email=str(order_record.get("buyer_email", "")),
            role="member",
        )
        if buyer_username
        else None
    )

    order_defaults = {
        "order_no": str(order_record.get("order_no") or f"ORDER{order_id}"),
        "buyer": buyer,
        "status": order_record.get("status", ORDER_STATUS_CONFIRMED),
        "shipping_method": order_record.get("shipping_method", SHIPPING_METHOD_HOME_DELIVERY),
        "payment_method": order_record.get("payment_method", PAYMENT_METHOD_NEWEBPAY),
        "payment_status": order_record.get("payment_status", PAYMENT_STATUS_PENDING),
        "payment_trade_no": order_record.get("payment_trade_no", ""),
        "payment_merchant_order_no": order_record.get("payment_merchant_order_no", ""),
        "buyer_email": order_record.get("buyer_email", ""),
        "buyer_username_snapshot": buyer_username,
        "buyer_display_name_snapshot": order_record.get("display_name", ""),
        "shipping_label": shipping_address.get("label", ""),
        "shipping_recipient": shipping_address.get("recipient", ""),
        "shipping_phone": shipping_address.get("phone", ""),
        "shipping_city": shipping_address.get("city", ""),
        "shipping_district": shipping_address.get("district", ""),
        "shipping_postal_code": shipping_address.get("postal_code", ""),
        "shipping_address_line": shipping_address.get("address_line", ""),
        "pickup_store_code": order_record.get("pickup_store_code", ""),
        "pickup_store_name": order_record.get("pickup_store_name", ""),
        "pickup_store_address": order_record.get("pickup_store_address", ""),
        "pickup_store_type": order_record.get("pickup_store_brand", ""),
        "pickup_recipient": shipping_address.get("recipient", ""),
        "pickup_phone": shipping_address.get("phone", ""),
        "invoice_type": invoice_profile.get("invoice_type", "personal"),
        "invoice_carrier_code": invoice_profile.get("carrier_code", ""),
        "invoice_company_name": invoice_profile.get("company_name", ""),
        "invoice_tax_id": invoice_profile.get("tax_id", ""),
        "subtotal_amount": Decimal(str((order_record.get("totals") or {}).get("subtotal", "0"))),
        "shipping_amount": Decimal(str((order_record.get("totals") or {}).get("shipping", "0"))),
        "discount_amount": Decimal(str((order_record.get("totals") or {}).get("discount", "0"))),
        "total_amount": Decimal(str((order_record.get("totals") or {}).get("total", "0"))),
        "note": order_record.get("buyer_note", ""),
        "paid_at": parse_datetime(order_record.get("payment_completed_at", "")) if order_record.get("payment_completed_at") else None,
        "completed_at": parse_datetime(order_record.get("completed_at", "")) if order_record.get("completed_at") else None,
        "cancelled_at": parse_datetime(order_record.get("cancelled_at", "")) if order_record.get("cancelled_at") else None,
    }
    order_model, _ = OrderModel.objects.update_or_create(id=order_id, defaults=order_defaults)

    OrderItemModel.objects.filter(order=order_model).delete()
    for line in order_record.get("items", []):
        product = ProductModel.objects.filter(slug=line.get("slug", "")).first()
        variant = None
        variant_id = str(line.get("variant_id", "")).strip()
        if product and variant_id:
            variant = product.variants.filter(external_variant_id=variant_id).first()
            if variant is None and line.get("sku"):
                variant = product.variants.filter(sku=line.get("sku", "")).first()
        seller = (
            _ensure_db_user_from_username(
                str(line.get("seller_username", "")).strip(),
                display_name=str(line.get("seller_display_name", "")),
                role="seller",
            )
            if line.get("seller_username")
            else None
        )
        OrderItemModel.objects.create(
            order=order_model,
            product=product,
            product_variant=variant,
            seller=seller,
            quantity=int(line.get("qty", 1)),
            unit_price=Decimal(str(line.get("price", "0"))),
            line_total=Decimal(str(line.get("line_total", "0"))),
            product_slug_snapshot=line.get("slug", ""),
            product_name_snapshot=line.get("name", ""),
            product_display_name_snapshot=line.get("display_name", "") or line.get("name", ""),
            variant_external_id_snapshot=variant_id,
            variant_name_snapshot=line.get("variant_name", ""),
            sku_snapshot=line.get("sku", ""),
            seller_username_snapshot=line.get("seller_username", ""),
            seller_display_name_snapshot=line.get("seller_display_name", ""),
            seller_status=line.get("seller_status", SELLER_STATUS_PENDING),
            tracking_number=line.get("tracking_number", ""),
            shipping_note=line.get("shipping_note", ""),
            shipped_at=parse_datetime(line.get("shipped_at", "")) if line.get("shipped_at") else None,
            completed_at=parse_datetime(line.get("completed_at", "")) if line.get("completed_at") else None,
        )

    service_request = order_record.get("service_request") or {}
    OrderServiceRequestModel.objects.filter(order=order_model).delete()
    if service_request.get("type") and service_request.get("status"):
        OrderServiceRequestModel.objects.create(
            order=order_model,
            user=buyer,
            request_type=_service_request_type_to_model(service_request.get("type", "")),
            status=_service_request_status_to_model(service_request.get("status", "")),
            reason=service_request.get("reason", ""),
            note=service_request.get("note", ""),
            reviewed_at=parse_datetime(service_request.get("reviewed_at", "")) if service_request.get("reviewed_at") else None,
        )

    ShipmentEventModel.objects.filter(order=order_model).delete()
    for item in order_model.items.all():
        if item.seller_status == SELLER_STATUS_PENDING:
            continue
        happened_at = item.completed_at or item.shipped_at or order_model.created_at
        if happened_at:
            ShipmentEventModel.objects.create(
                order=order_model,
                order_item=item,
                event_type=_shipment_event_type_for_line_status(item.seller_status),
                tracking_number=item.tracking_number,
                note=item.shipping_note,
                operator=item.seller,
                happened_at=happened_at,
            )

    _sync_payment_record_to_orm(order_model, order_record)
    return order_model


# checkout 配送方式主設定：
# - 給購物車與 checkout 頁共用
# - 依 LOGISTICS_CHECKOUT_ENABLED 決定是否開放超商取貨
def get_checkout_shipping_methods() -> List[Dict[str, str]]:
    # checkout 可用配送方式清單；若物流流程關閉，僅保留宅配。
    """回傳目前 checkout 可選的配送方式。

    用途：
    - 提供 checkout 頁面渲染配送方式選單
    - 依 `LOGISTICS_CHECKOUT_ENABLED` 控制是否開放超商取貨
    """
    if not LOGISTICS_CHECKOUT_ENABLED:
        return [dict(SHIPPING_METHOD_CHOICES[0])]
    if not LOGISTICS_CHECKOUT_ENABLED:
        return [dict(SHIPPING_METHOD_CHOICES[0])]
    return [dict(item) for item in SHIPPING_METHOD_CHOICES]


# 配送方式驗證：
# - 檢查前端送來的配送方式是否仍在目前允許名單中
def is_checkout_shipping_method_enabled(shipping_method: str) -> bool:
    # 用統一入口判斷某個配送方式是否真的能出現在 checkout。
    """檢查指定配送方式目前是否允許在 checkout 使用。"""
    return shipping_method in {item["value"] for item in get_checkout_shipping_methods()}


# 配送方式正規化：
# - 若前端送來無效值，回退到宅配到府
def normalize_checkout_shipping_method(shipping_method: str) -> str:
    # 把外部輸入正規化成可接受值；不合法時退回宅配，避免前端帶入未知字串。
    """把前端送來的配送方式正規化成目前可接受的值。"""
    candidate = (shipping_method or "").strip()
    if is_checkout_shipping_method_enabled(candidate):
        return candidate
    return SHIPPING_METHOD_HOME_DELIVERY


# Decimal 工具：
# - 統一處理運費 / 免運門檻等數值設定
def _shipping_decimal(value: Any, default: str = "0.00") -> Decimal:
    # 運費規則可能來自環境變數、JSON 或 ORM 欄位，這裡統一安全轉成 Decimal。
    """把運費與免運門檻等設定值轉成 Decimal。"""
    try:
        return Decimal(str(value if value not in (None, "") else default)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal(default).quantize(Decimal("0.01"))


def _format_created_at(value: str) -> str:
    # 訂單列表與報表都會把 ISO datetime 轉成前端可直接顯示的本地時間字串。
    """格式化 訂單 流程中使用的時間或顯示值。

    參數:
        value: 待格式化、待解析或待判斷的值。

    回傳:
        依函式用途回傳對應資料。
    """
    parsed = parse_datetime(value) if value else None
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M") if parsed else ""


def _serialize_totals(totals: Dict[str, Decimal]) -> Dict[str, str]:
    # totals 在 API 與 JSON snapshot 中一律用字串保存，避免浮點格式差異。
    """把 訂單 相關資料整理成較適合輸出或渲染的格式。

    參數:
        totals: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    return {key: format(value, ".2f") for key, value in totals.items()}


def _line_decimal(value: Any) -> Decimal:
    # 單筆商品 line_total / price 計算時都走這裡，保持精度一致。
    """處理 訂單 相關流程。

    參數:
        value: 待格式化、待解析或待判斷的值。

    回傳:
        數值結果，供後續金額或庫存流程使用。
    """
    return Decimal(str(value)).quantize(Decimal("0.01"))


# 單商品運費計算：
# - 先看商品是否覆寫 seller shipping rules
# - 再依配送方式決定要取宅配還是超商運費
def _shipping_fee_for_line(product: Dict[str, Any], seller_rules: Dict[str, Any], shipping_method: str) -> Decimal:
    # 商品可沿用賣家規則，或在商品層覆寫運費；這裡統一決定實際基礎運費。
    """計算單一商品在指定配送方式下的實際運費。"""
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


# 賣家分組配送能力計算：
# - 同一賣家群組內，只保留所有商品共同支援的配送方式
def _available_shipping_methods_for_group(
    lines: List[Dict[str, Any]],
    seller_rules: Dict[str, Any],
) -> List[Dict[str, str]]:
    # 同一賣家的一組商品必須找出所有品項都支援的配送方式，checkout 才能安全套用。
    """計算同一賣家分組內所有商品共同支援的配送方式。"""
    if not LOGISTICS_CHECKOUT_ENABLED:
        return [{"value": SHIPPING_METHOD_HOME_DELIVERY, "label": SHIPPING_METHOD_LABELS[SHIPPING_METHOD_HOME_DELIVERY]}]
    available: list[dict[str, str]] = []
    can_use_home = bool(seller_rules.get("home_delivery_enabled", True))
    can_use_store = bool(seller_rules.get("convenience_store_enabled", True))

    for line in lines:
        product = product_management.get_product_for_admin(line["slug"]) or {}
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


# 賣家分組運費主流程：
# - 先依 seller 分組
# - 再計算每組的 subtotal / shipping_fee / free_shipping_threshold
# - 這是購物車、checkout、訂單頁共用的資料基礎
def build_seller_shipping_groups(
    items: List[Dict[str, Any]],
    *,
    shipping_method: str,
) -> List[Dict[str, Any]]:
    # 先依 seller 分組，再為每組補上 subtotal / shipping_fee / 可用配送方式。
    # checkout、買家訂單詳情、賣家訂單詳情都會共用這份結構。
    """依賣家拆分購物車 / 訂單商品，並計算每位賣家的運費分組。

    前端使用頁面：
    - 購物車頁的分賣家運費摘要
    - checkout 頁的運費預估
    - 買家訂單詳情頁 / 賣家訂單詳情頁的出貨分組

    功能：
    - 將商品依賣家分組
    - 計算每組 subtotal、shipping_fee、free_shipping_threshold
    - 產生每組可用配送方式清單
    """
    grouped: Dict[str, Dict[str, Any]] = {}
    for raw_line in items:
        line = dict(raw_line)
        if "line_total" not in line:
            line["line_total"] = format(Decimal(str(line["price"])) * int(line["qty"]), ".2f")
        product = product_management.get_product_for_admin(line["slug"]) or {}
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
            product = product_management.get_product_for_admin(line["slug"]) or {}
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


# checkout totals 主流程：
# - 依目前購物車、折扣、配送方式，回傳完整金額摘要
def build_checkout_totals(
    session,
    *,
    shipping_method: str,
) -> Dict[str, Any]:
    # checkout 金額不是只算 subtotal；還要同時計算分賣家運費群組與不支援的賣家名單。
    """依目前購物車與配送方式計算 checkout totals。

    前端使用頁面：
    - 購物車頁
    - checkout 頁

    功能：
    - 套用優惠券
    - 依賣家分組計算運費
    - 回傳 subtotal / shipping / discount / total 與 seller shipping groups
    """
    shipping_method = normalize_checkout_shipping_method(shipping_method)
    cart = cart_service.get_cart(session)
    items = list(cart.get("items", {}).values())
    _log_checkout_checkpoint(
        "build_totals_loaded_cart",
        shipping_method=shipping_method,
        cart_item_count=len(items),
        item_summary=_checkout_item_debug_summary(items),
    )
    subtotal = sum((Decimal(str(item["price"])) * int(item["qty"]) for item in items), Decimal("0.00")).quantize(Decimal("0.01"))
    discount = cart_service.compute_totals(session)["discount"]
    seller_shipping_groups = build_seller_shipping_groups(items, shipping_method=shipping_method)
    unsupported_groups = [group for group in seller_shipping_groups if not group["selected_shipping_method_supported"]]

    shipping = sum((_shipping_decimal(group["shipping_fee"]) for group in seller_shipping_groups), Decimal("0.00")).quantize(Decimal("0.01"))
    total = (subtotal + shipping - discount).quantize(Decimal("0.01"))
    _log_checkout_checkpoint(
        "build_totals_computed",
        shipping_method=shipping_method,
        subtotal=str(subtotal),
        shipping=str(shipping),
        discount=str(discount),
        total=str(total),
        seller_count=len(seller_shipping_groups),
        unsupported_sellers=[group["seller_display_name"] for group in unsupported_groups],
    )
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
        seller = auth_demo.get_user_by_username(str(item["seller_username"]))
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
    # 只有訂單仍在 confirmed、且沒有進行中的售後時，才允許買家整單取消。
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
    # 退款申請只開放給已有出貨進度的訂單，避免和尚未出貨的取消流程混用。
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
    # 所有訂單明細都到達已出貨或已完成後，買家才可以做最終確認收貨。
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
    # 這裡會把訂單補齊顯示標籤、售後狀態、付款狀態、門市資訊與 seller shipping groups，
    # 讓前台訂單詳情、會員中心和管理端共用同一份訂單 payload。
    # 將原始訂單記錄補成前台 / 後台都能直接顯示的 canonical payload。
    """處理 訂單 相關流程。

    參數:
        order: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    item = dict(order)
    if not item.get("buyer_user_id") and item.get("username"):
        buyer = auth_demo.get_user_by_username(str(item["username"]))
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


# 建單主流程：
# - 由 checkout confirm API 呼叫
# - 驗證地址、配送、付款方式與購物車內容
# - 計算 totals、預留庫存、建立訂單 snapshot
# - 成功後清空購物車
# checkout confirm 的主流程如下：
# 1. 驗證 cart、地址、配送方式、付款方式
# 2. 重算 totals 與 seller shipping groups，避免直接信任前端 snapshot
# 3. 扣庫存並建立訂單 item snapshot
# 4. 將同一份訂單結果同步寫入 ORM 與 JSON fallback
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
    """將目前購物車內容結帳成正式訂單。"""
    # 這裡會重新驗證 cart、地址、配送方式與付款方式，並重算 totals，
    # 避免直接信任前端 checkout snapshot。
    # 建單完成後會保留當下的地址、發票、配送與付款快照，
    # 後續即使使用者修改個人資料，也不會反向影響既有訂單。
    # checkout confirm 的主流程會重新驗證 cart、重算 totals、建立訂單 items，
    # 最後再把 snapshot 同步寫回 ORM / JSON。
    # 建單完成後會保留 checkout 當下的地址、發票、配送與付款快照，
    # 後續即使使用者修改個人資料，也不會反向影響既有訂單。
    # 這是 checkout confirm 的核心入口。
    # 主要順序是：
    # 1. 驗證 cart / 配送 / 付款 / 地址
    # 2. 計算 totals 並確認所有賣家都支援所選配送方式
    # 3. 預留庫存
    # 4. 建立訂單 snapshot，最後同步到 ORM / JSON
    """把購物車內容轉成正式訂單，並清空已結帳品項。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。
        user: 目前操作中的會員快照資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    cart = cart_service.get_cart(session)
    items = list(cart.get("items", {}).values())
    _log_checkout_checkpoint(
        "create_order_loaded_cart",
        username=user.get("username", ""),
        shipping_method=shipping_method,
        payment_method=payment_method,
        address_id=address_id,
        cart_item_count=len(items),
        item_summary=_checkout_item_debug_summary(items),
    )
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
    _log_checkout_checkpoint(
        "create_order_selected_address",
        username=user.get("username", ""),
        address_id=address_id,
        has_selected_address=bool(selected_address),
        shipping_method=shipping_method,
    )
    if not selected_address:
        raise ValueError("Please select a shipping address.")

    checkout_pricing = build_checkout_totals(session, shipping_method=shipping_method)
    _log_checkout_checkpoint(
        "create_order_pricing_ready",
        username=user.get("username", ""),
        shipping_method=shipping_method,
        totals={key: str(value) for key, value in checkout_pricing["totals"].items()},
        seller_count=len(checkout_pricing["seller_shipping_groups"]),
        unsupported_sellers=checkout_pricing["unsupported_sellers"],
    )
    if checkout_pricing["unsupported_sellers"]:
        raise ValueError(
            "The selected shipping method is not available for: "
            + ", ".join(checkout_pricing["unsupported_sellers"])
            + "."
        )
    _log_checkout_checkpoint(
        "create_order_before_reserve_stock",
        username=user.get("username", ""),
        cart_item_count=len(items),
    )
    product_management.reserve_stock(items)
    _log_checkout_checkpoint(
        "create_order_after_reserve_stock",
        username=user.get("username", ""),
        cart_item_count=len(items),
    )
    totals = checkout_pricing["totals"]
    db_orders_enabled = _db_orders_enabled()
    if db_orders_enabled:
        latest_order = OrderModel.objects.order_by("-id").only("id").first()
        next_id = latest_order.id + 1 if latest_order else 1
    else:
        json_orders = local_store.get_orders()
        next_id = max((int(order["id"]) for order in json_orders if order.get("id")), default=0) + 1
    _log_checkout_checkpoint(
        "create_order_next_id_resolved",
        username=user.get("username", ""),
        db_orders_enabled=db_orders_enabled,
        next_order_id=next_id,
    )

    user_record = auth_demo.get_user_by_username(user["username"]) or {}
    db_user = _ensure_db_user_from_username(
        user["username"],
        display_name=user.get("display_name", ""),
        email=user_record.get("email", ""),
        role="member",
    )
    _log_checkout_checkpoint(
        "create_order_user_resolved",
        username=user.get("username", ""),
        has_db_user=bool(db_user),
        buyer_email=(user_record.get("email", "") or (db_user.email if db_user else "")),
    )

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
                "seller_user_id": product.get("owner_user_id"),
                "seller_username": product.get("owner_username", ""),
                "seller_display_name": product.get("owner_display_name", ""),
                "seller_status": SELLER_STATUS_PENDING,
                "shipping_note": "",
                "tracking_number": "",
                "shipped_at": "",
                "completed_at": "",
            }
            for item in items
            for product in [product_management.get_product_for_admin(item["slug"]) or {}]
        ],
        "totals": _serialize_totals(totals),
        "created_at": timezone.localtime().isoformat(),
        "buyer_email": user_record.get("email", "") or (db_user.email if db_user else ""),
    }
    _log_checkout_checkpoint(
        "create_order_payload_built",
        username=user.get("username", ""),
        order_id=order["id"],
        order_item_count=len(order["items"]),
        payment_method=order["payment_method"],
        shipping_method=order["shipping_method"],
        pickup_store_code=order["pickup_store_code"],
    )
    order = _persist_order_record(order)
    _log_checkout_checkpoint(
        "create_order_persisted",
        username=user.get("username", ""),
        order_id=order["id"],
        payment_status=order.get("payment_status", ""),
        item_count=len(order.get("items", [])),
    )
    cart_service.clear(session)
    _log_checkout_checkpoint(
        "create_order_cart_cleared",
        username=user.get("username", ""),
        order_id=order["id"],
    )
    return order


# 買家訂單列表：
# - 給會員中心 / 我的訂單列表使用
# - 補上 shipment groups 與狀態摘要，方便前端直接渲染
def list_orders_for_user(username: str) -> List[Dict[str, Any]]:
    # 買家列表頁只看自己的訂單，並額外補上 shipment groups / summary 供 UI 直接顯示。
    """列出 訂單 相關資料，供頁面或 API 顯示。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    results = []
    for order in _merged_order_records():
        if order.get("username") != username:
            continue
        item = _enrich_order_common(order)
        shipment_groups = _build_buyer_shipment_groups(item.get("items", []))
        item["shipment_groups"] = shipment_groups
        item["shipment_summary"] = " / ".join(group["seller_status_label"] for group in shipment_groups) or "待出貨"
        results.append(item)
    return results


# checkout 設定輔助：
# - 回傳前端配送方式選單
def get_checkout_shipping_methods() -> List[Dict[str, str]]:
    # 這裡是較晚一層的公開 getter，直接回傳配送方式給 checkout API 使用。
    """回傳 checkout 可選的物流方式。"""
    return [dict(item) for item in SHIPPING_METHOD_CHOICES]


# checkout 設定輔助：
# - 回傳前端付款方式選單
def get_checkout_payment_methods() -> List[Dict[str, str]]:
    # 付款方式目前仍是固定選單，集中從 service 層提供給 checkout preview。
    """回傳 checkout 可選的付款方式。"""
    return [dict(item) for item in PAYMENT_METHOD_CHOICES]


# checkout 設定輔助：
# - 回傳超商取貨可選品牌
def get_convenience_store_brands() -> List[Dict[str, str]]:
    # 超商選店品牌只在物流流程開啟時對前端可見。
    """回傳 checkout 可選的超商品牌。"""
    if not LOGISTICS_CHECKOUT_ENABLED:
        return []
    return [dict(item) for item in CONVENIENCE_STORE_BRAND_CHOICES]


# 買家訂單明細：
# - 給買家訂單詳情頁使用
# - 會補齊 seller line 與 shipment groups
def get_order_detail_for_user(order_id: int, username: str) -> Optional[Dict[str, Any]]:
    # 買家單筆訂單詳情會把 line item 再 enrich，一併補出 shipment groups。
    """取得 訂單 流程中指定條件的資料。

    參數:
        order_id: 訂單編號。
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    order = next((item for item in _merged_order_records() if item.get("id") == order_id), None)
    if not order or order.get("username") != username:
        return None
    item = _enrich_order_common(order)
    item["items"] = [_enrich_seller_line(line) for line in item.get("items", [])]
    item["shipment_groups"] = _build_buyer_shipment_groups(item["items"])
    return item


# 售後申請：
# - 建立取消或退款請求
# - 由買家訂單頁送出，後續交由賣家 / staff 審核
def request_order_service(order_id: int, username: str, *, request_type: str, reason: str) -> Dict[str, Any]:
    # 買家售後入口只允許建立 pending request；真正核准/拒絕會交由 staff 後續處理。
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

    order = _merged_order_record_by_id(order_id)
    if order and order.get("username") == username:
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
        refreshed = _persist_order_record(order)
        return _enrich_order_common(refreshed)
    raise ValueError("Order not found.")


# 訂單完成：
# - 買家在賣家已出貨後確認收貨
# - 會把可完成的 seller line 改成 completed
def confirm_order_completion(order_id: int, username: str) -> Dict[str, Any]:
    # 買家確認收貨後，會把所有可完成的 seller line 推進到 completed。
    """Allow the buyer to confirm receipt and complete the order."""
    order = _merged_order_record_by_id(order_id)
    if order and order.get("username") == username:
        if not _can_confirm_completion(order):
            raise ValueError("This order is not ready for buyer completion yet.")
        completed_at = timezone.localtime().isoformat()
        for line in order.get("items", []):
            if line.get("seller_status") in {SELLER_STATUS_SHIPPED, SELLER_STATUS_COMPLETED}:
                if not line.get("shipped_at"):
                    line["shipped_at"] = completed_at
                line["seller_status"] = SELLER_STATUS_COMPLETED
                line["completed_at"] = completed_at
        order["completed_at"] = completed_at
        refreshed = _persist_order_record(order)
        item = _enrich_order_common(refreshed)
        item["items"] = [_enrich_seller_line(line) for line in item.get("items", [])]
        item["shipment_groups"] = _build_buyer_shipment_groups(item["items"])
        return item
    raise ValueError("Order not found.")


# 藍新付款結果回寫：
# - 只接受 callback / return / query 真正帶回的資料
# - 更新付款方式、付款狀態、藍新交易序號
# - 若有超商門市資料，也同步回寫到訂單
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
    # 藍新 callback / return / query 統一回寫這裡，避免付款狀態分散在不同流程各自更新。
    """Persist NewebPay callback data back onto the stored order."""
    order = _merged_order_record_by_id(order_id)
    if order:
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

        refreshed = _persist_order_record(order)
        return _enrich_order_common(refreshed)
    return None


def _build_seller_order_view(order: Dict[str, Any], seller_username: str) -> Optional[Dict[str, Any]]:
    # 賣家視角只保留屬於自己的 line items，並重算該賣家的履約狀態與小計。
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


# 賣家訂單列表：
# - 給賣家訂單頁使用
# - 依日期條件列出賣家需要履約的訂單
def list_orders_for_seller(username: str, *, date_from: str = "", date_to: str = "") -> List[Dict[str, Any]]:
    # 賣家列表頁是從全量訂單過濾出「這位賣家有參與的訂單」，再套日期條件。
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
    for order in _merged_order_records():
        if not _matches_date_filter(order, filters):
            continue
        seller_order = _build_seller_order_view(order, username)
        if seller_order:
            items.append(seller_order)
    return items


# 賣家訂單明細：
# - 給賣家查看收件、付款摘要、商品分組與出貨資訊
def get_order_detail_for_seller(order_id: int, username: str) -> Optional[Dict[str, Any]]:
    # 單筆賣家訂單詳情沿用 seller view builder，保持列表與詳情看到同一套履約欄位。
    """取得 訂單 流程中指定條件的資料。

    參數:
        order_id: 訂單編號。
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    order = next((item for item in _merged_order_records() if item.get("id") == order_id), None)
    if not order:
        return None
    return _build_seller_order_view(order, username)


# 賣家履約更新：
# - 保存賣家端出貨狀態、物流單號、出貨備註
def update_seller_order(
    order_id: int,
    seller_username: str,
    *,
    seller_status: str,
    shipping_note: str = "",
    tracking_number: str = "",
) -> Dict[str, Any]:
    # 賣家可更新自己的 seller line 狀態、物流單號與備註；其他賣家的 line 不會受影響。
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

    order = _merged_order_record_by_id(order_id)
    if order:
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
        refreshed = _persist_order_record(order)
        return _build_seller_order_view(refreshed or order, seller_username) or {}
    raise ValueError("Order not found.")


# 銷售報表：
# - 給賣家報表頁使用
# - 統計訂單數、銷量、營收與熱賣商品
def build_sales_report(username: str, *, date_from: str = "", date_to: str = "") -> Dict[str, Any]:
    # 報表目前完全從賣家可見訂單推導，不另外建立聚合表，方便先維持 JSON/ORM 雙軌相容。
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
    # 管理端視角保留完整訂單，不裁切 seller line，並補上 shipment groups 與 seller_count。
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


# 管理端訂單列表：
# - 給 staff 訂單管理頁使用
# - 可依日期、狀態、售後狀態與關鍵字篩選
def list_orders_for_admin(
    *,
    date_from: str = "",
    date_to: str = "",
    status: str = "",
    service_status: str = "",
    q: str = "",
) -> List[Dict[str, Any]]:
    # 管理端訂單列表會在平台視角套日期、主狀態、售後狀態與關鍵字查詢。
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
    for order in _merged_order_records():
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


# 管理端訂單明細：
# - 不受買家 / 賣家擁有權限制
# - 用於 staff 查看完整訂單與售後資訊
def get_order_detail_for_admin(order_id: int) -> Optional[Dict[str, Any]]:
    # staff 單筆詳情直接看完整 admin view，不受 buyer / seller 所有權限制。
    """取得 訂單 流程中指定條件的資料。

    參數:
        order_id: 訂單編號。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    order = next((item for item in _merged_order_records() if item.get("id") == order_id), None)
    if not order:
        return None
    return _build_admin_order_view(order)


# 售後審核：
# - 由 staff 審核取消 / 退款請求
# - 核准後可改變訂單狀態並在取消時回補庫存
def review_service_request(order_id: int, *, approved: bool, note: str = "") -> Dict[str, Any]:
    # 這裡是 staff 真正改變售後結果的入口；核准取消時也會同步回補庫存。
    """由管理員審核買家的售後申請。

    參數:
        order_id: 訂單編號。
        approved: 是否核准此次審核或申請。
        note: 補充說明、審核備註或操作備註。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    order = _merged_order_record_by_id(order_id)
    if order:
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

        refreshed = _persist_order_record(order)
        return _build_admin_order_view(refreshed)
    raise ValueError("Order not found.")


# 管理端摘要：
# - 提供 dashboard 需要的訂單總數、取消、退款、待處理售後統計
def build_admin_order_summary() -> Dict[str, Any]:
    # dashboard 摘要只取平台視角已整理過的訂單，避免重複寫一套統計邏輯。
    """彙整平台管理端的訂單摘要統計。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    orders = [_build_admin_order_view(order) for order in _merged_order_records()]
    pending_requests = [order for order in orders if order["service_request"]["status"] == SERVICE_REQUEST_PENDING]
    return {
        "order_count": len(orders),
        "confirmed_count": len([order for order in orders if order["status"] == ORDER_STATUS_CONFIRMED]),
        "cancelled_count": len([order for order in orders if order["status"] == ORDER_STATUS_CANCELLED]),
        "refunded_count": len([order for order in orders if order["status"] == ORDER_STATUS_REFUNDED]),
        "pending_service_requests": len(pending_requests),
        "latest_service_requests": pending_requests[:5],
    }
