"""藍新物流 mock 測試 service。

這一層先模擬藍新物流建立托運單與 callback 更新流程，方便在沒有資料庫、
沒有正式物流憑證的情況下，先把後端 API、欄位與測試骨架建立起來。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from django.utils import timezone

from ..repositories import local_store
from . import orders as order_service

PROVIDER_NAME = "NewebPay Logistics"
MODE_NAME = "mock"
STATUS_CREATED = "created"
STATUS_PICKED_UP = "picked_up"
STATUS_DELIVERED = "delivered"
STATUS_FAILED = "failed"


def _now_iso() -> str:
    """回傳目前本地時間 ISO 字串。"""
    return timezone.localtime().isoformat()


def _build_logistics_no(order_id: int) -> str:
    """建立 mock 物流單號。"""
    stamp = timezone.localtime().strftime("%Y%m%d%H%M%S")
    return f"NLOG-{order_id}-{stamp}"


def _latest_seller_order(order_id: int, username: str) -> Dict[str, Any]:
    """取得指定賣家可見的訂單資料。"""
    order = order_service.get_order_detail_for_seller(order_id, username)
    if not order:
        raise ValueError("Order not found.")
    return order


def _serialize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """統一物流 mock 回傳格式。"""
    return {
        "provider": record["provider"],
        "mode": record["mode"],
        "order_id": record["order_id"],
        "seller_username": record["seller_username"],
        "merchant_order_no": record.get("merchant_order_no", ""),
        "logistics_no": record["logistics_no"],
        "status": record["status"],
        "status_label": record["status_label"],
        "store_type": record["store_type"],
        "temperature": record["temperature"],
        "receiver_name": record["receiver_name"],
        "receiver_phone": record["receiver_phone"],
        "shipment_note": record.get("shipment_note", ""),
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "callback_count": record.get("callback_count", 0),
        "raw_payload": record.get("raw_payload", {}),
    }


def get_logistics_record(order_id: int, seller_username: str) -> Optional[Dict[str, Any]]:
    """取得某張賣家訂單最新的藍新物流 mock 紀錄。"""
    _latest_seller_order(order_id, seller_username)
    records = [
        item
        for item in local_store.get_newebpay_logistics_logs()
        if item.get("order_id") == order_id and item.get("seller_username") == seller_username
    ]
    if not records:
        return None
    records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return _serialize_record(records[0])


def create_logistics_request(
    order_id: int,
    seller_username: str,
    *,
    store_type: str = "UNIMARTC2C",
    temperature: str = "normal",
    shipment_note: str = "",
) -> Dict[str, Any]:
    """建立藍新物流 mock 托運請求。"""
    order = _latest_seller_order(order_id, seller_username)
    shipping = order.get("shipping_address") or {}
    logs = list(local_store.get_newebpay_logistics_logs())
    now = _now_iso()
    record = {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "order_id": order_id,
        "seller_username": seller_username,
        "logistics_no": _build_logistics_no(order_id),
        "status": STATUS_CREATED,
        "status_label": "已建立托運單",
        "store_type": store_type.strip() or "UNIMARTC2C",
        "temperature": temperature.strip() or "normal",
        "receiver_name": shipping.get("recipient", ""),
        "receiver_phone": shipping.get("phone", ""),
        "shipment_note": shipment_note.strip(),
        "created_at": now,
        "updated_at": now,
        "callback_count": 0,
        "raw_payload": {
            "seller_item_count": len(order.get("items", [])),
            "shipping_city": shipping.get("city", ""),
        },
    }
    logs.append(record)
    local_store.save_newebpay_logistics_logs(logs)
    return _serialize_record(record)


def handle_logistics_callback(
    *,
    logistics_no: str,
    status_value: str,
    result_message: str = "",
    raw_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """模擬藍新物流 callback。"""
    normalized = str(status_value).strip().lower()
    if normalized not in {STATUS_CREATED, STATUS_PICKED_UP, STATUS_DELIVERED, STATUS_FAILED}:
        raise ValueError("Invalid mock logistics status.")

    logs = list(local_store.get_newebpay_logistics_logs())
    for record in logs:
        if record.get("logistics_no") != logistics_no:
            continue
        record["status"] = normalized
        record["status_label"] = {
            STATUS_CREATED: "已建立托運單",
            STATUS_PICKED_UP: "已取件",
            STATUS_DELIVERED: "已送達",
            STATUS_FAILED: "配送失敗",
        }[normalized]
        record["updated_at"] = _now_iso()
        record["callback_count"] = int(record.get("callback_count", 0)) + 1
        payload = dict(raw_payload or {})
        if result_message:
            payload["result_message"] = result_message
        record["raw_payload"] = payload
        local_store.save_newebpay_logistics_logs(logs)
        return _serialize_record(record)
    raise ValueError("Logistics trade not found.")
