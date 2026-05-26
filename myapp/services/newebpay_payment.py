"""藍新支付 mock 測試 service。

這一層不是正式串接藍新支付 SDK，而是先建立可測試的 API 架構：
- 建立付款交易請求
- 查詢交易狀態
- 模擬藍新支付 callback / webhook 回傳

未來若要改成正式串接，可保留對外函式名稱，將內部 JSON 寫入改為
資料庫與真實藍新 API 呼叫。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from django.utils import timezone

from ..repositories import local_store
from . import orders as order_service

PROVIDER_NAME = "NewebPay Payment"
MODE_NAME = "mock"
STATUS_PENDING = "pending"
STATUS_PAID = "paid"
STATUS_FAILED = "failed"


def _now_iso() -> str:
    """回傳目前本地時間 ISO 字串。"""
    return timezone.localtime().isoformat()


def _serialize_amount(value: Any) -> str:
    """把金額統一轉成兩位小數字串，方便 JSON 與前端顯示。"""
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def _build_trade_no(order_id: int) -> str:
    """建立 mock 交易編號。

    正式版通常由金流或後端訂單邏輯生成唯一編號；這裡先用時間戳與訂單編號組合。
    """
    stamp = timezone.localtime().strftime("%Y%m%d%H%M%S")
    return f"NPAY-{order_id}-{stamp}"


def _latest_order_record(order_id: int, username: str) -> Dict[str, Any]:
    """取得指定買家的訂單詳情，找不到就丟出錯誤。"""
    order = order_service.get_order_detail_for_user(order_id, username)
    if not order:
        raise ValueError("Order not found.")
    return order


def _serialize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """統一回傳前端/DRF 使用的支付交易結構。"""
    return {
        "provider": record["provider"],
        "mode": record["mode"],
        "order_id": record["order_id"],
        "buyer_username": record["buyer_username"],
        "merchant_order_no": record["merchant_order_no"],
        "trade_no": record["trade_no"],
        "status": record["status"],
        "status_label": record.get("status_label", ""),
        "amount": record["amount"],
        "currency": record.get("currency", "TWD"),
        "payment_url": record["payment_url"],
        "return_url": record.get("return_url", ""),
        "client_back_url": record.get("client_back_url", ""),
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "paid_at": record.get("paid_at", ""),
        "note": record.get("note", ""),
        "callback_count": record.get("callback_count", 0),
        "raw_payload": record.get("raw_payload", {}),
    }


def get_payment_record(order_id: int, username: str) -> Optional[Dict[str, Any]]:
    """取得某張訂單最新的藍新支付 mock 紀錄。"""
    _latest_order_record(order_id, username)
    records = [
        item
        for item in local_store.get_newebpay_payment_logs()
        if item.get("order_id") == order_id and item.get("buyer_username") == username
    ]
    if not records:
        return None
    records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return _serialize_record(records[0])


def create_payment_request(
    order_id: int,
    username: str,
    *,
    return_url: str = "",
    client_back_url: str = "",
    note: str = "",
) -> Dict[str, Any]:
    """建立藍新支付 mock 付款請求。

    Args:
        order_id: 要付款的訂單編號。
        username: 目前登入買家帳號。
        return_url: 模擬金流完成後回到商店的後端通知網址。
        client_back_url: 模擬前端付款完成後導回的頁面網址。
        note: 測試備註。
    """
    order = _latest_order_record(order_id, username)
    records = list(local_store.get_newebpay_payment_logs())
    amount = _serialize_amount(order.get("totals", {}).get("total", order.get("total_amount", "0.00")))
    now = _now_iso()
    trade_no = _build_trade_no(order_id)
    merchant_order_no = f"ORDER-{order_id}-{timezone.localtime().strftime('%H%M%S')}"
    record = {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "order_id": order_id,
        "buyer_username": username,
        "merchant_order_no": merchant_order_no,
        "trade_no": trade_no,
        "status": STATUS_PENDING,
        "status_label": "待付款",
        "amount": amount,
        "currency": "TWD",
        "payment_url": f"https://mock.newebpay.local/pay/{trade_no}",
        "return_url": return_url.strip(),
        "client_back_url": client_back_url.strip(),
        "created_at": now,
        "updated_at": now,
        "paid_at": "",
        "note": note.strip(),
        "callback_count": 0,
        "raw_payload": {
            "merchant_order_no": merchant_order_no,
            "order_snapshot_total": amount,
            "order_snapshot_items": len(order.get("items", [])),
        },
    }
    records.append(record)
    local_store.save_newebpay_payment_logs(records)
    return _serialize_record(record)


def handle_payment_callback(
    *,
    trade_no: str,
    status_value: str,
    paid_amount: str = "",
    result_message: str = "",
    raw_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """模擬藍新支付 callback。

    Args:
        trade_no: 交易編號。
        status_value: mock 狀態，支援 `paid` / `failed` / `pending`。
        paid_amount: callback 附帶的付款金額。
        result_message: callback 結果說明。
        raw_payload: 原始 callback 內容，方便之後排錯。
    """
    normalized = str(status_value).strip().lower()
    if normalized not in {STATUS_PENDING, STATUS_PAID, STATUS_FAILED}:
        raise ValueError("Invalid mock payment status.")

    records = list(local_store.get_newebpay_payment_logs())
    for record in records:
        if record.get("trade_no") != trade_no:
            continue
        record["status"] = normalized
        record["status_label"] = {
            STATUS_PENDING: "待付款",
            STATUS_PAID: "付款成功",
            STATUS_FAILED: "付款失敗",
        }[normalized]
        record["updated_at"] = _now_iso()
        record["callback_count"] = int(record.get("callback_count", 0)) + 1
        if normalized == STATUS_PAID:
            record["paid_at"] = _now_iso()
        if paid_amount:
            record["amount"] = _serialize_amount(paid_amount)
        payload = dict(raw_payload or {})
        if result_message:
            payload["result_message"] = result_message
        record["raw_payload"] = payload
        local_store.save_newebpay_payment_logs(records)
        return _serialize_record(record)
    raise ValueError("Payment trade not found.")
