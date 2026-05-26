"""藍新物流 sandbox / 正式串接前的 scaffold。

這個模組先不直接生成正式物流 API payload，原因是：
- 藍新物流可依啟用類型（超商店到店 / 宅配 / 大宗寄倉）有不同欄位
- 公開可直接引用的正式物流 API 文件不像 MPG 支付規格那麼穩定

因此這一版先提供：
- 環境變數設定檢查
- 訂單轉物流請求的欄位摘要
- callback 收件資料回存格式

後續只要拿到商店實際啟用物流模式與官方文件，就可以在這個 scaffold 上補正式簽章/請求。
"""

from __future__ import annotations

import os
from typing import Any, Dict

from . import orders as order_service

PROVIDER_NAME = "NewebPay Logistics"
MODE_NAME = "sandbox-scaffold"


class NewebpayLogisticsConfigurationError(RuntimeError):
    """藍新物流 scaffold 設定不足。"""


def _load_logistics_config() -> Dict[str, str]:
    """讀取藍新物流 scaffold 所需設定。"""
    config = {
        "merchant_id": os.getenv("NEWEBPAY_LOGISTICS_MERCHANT_ID", "").strip()
        or os.getenv("NEWEBPAY_MERCHANT_ID", "").strip(),
        "hash_key": os.getenv("NEWEBPAY_LOGISTICS_HASH_KEY", "").strip()
        or os.getenv("NEWEBPAY_HASH_KEY", "").strip(),
        "hash_iv": os.getenv("NEWEBPAY_LOGISTICS_HASH_IV", "").strip()
        or os.getenv("NEWEBPAY_HASH_IV", "").strip(),
        "callback_url": os.getenv("NEWEBPAY_LOGISTICS_CALLBACK_URL", "").strip(),
        "create_url": os.getenv("NEWEBPAY_LOGISTICS_CREATE_URL", "").strip(),
        "status_url": os.getenv("NEWEBPAY_LOGISTICS_STATUS_URL", "").strip(),
    }
    if not config["merchant_id"]:
        raise NewebpayLogisticsConfigurationError("Missing NEWEBPAY_LOGISTICS_MERCHANT_ID / NEWEBPAY_MERCHANT_ID")
    return config


def get_runtime_summary() -> Dict[str, Any]:
    """回傳物流 scaffold 可用性摘要。"""
    try:
        config = _load_logistics_config()
    except NewebpayLogisticsConfigurationError as exc:
        return {
            "provider": PROVIDER_NAME,
            "mode": MODE_NAME,
            "configured": False,
            "missing_settings": [str(exc)],
        }
    return {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "configured": True,
        "merchant_id": config["merchant_id"],
        "callback_url": config["callback_url"],
        "create_url": config["create_url"],
        "status_url": config["status_url"],
        "note": "此為物流 sandbox scaffold；正式欄位請依啟用物流模式補齊。",
    }


def prepare_logistics_request(
    order_id: int,
    seller_username: str,
    *,
    logistics_type: str = "UNIMARTC2C",
    shipment_note: str = "",
) -> Dict[str, Any]:
    """把目前訂單資料整理成藍新物流串接前的欄位摘要。"""
    config = _load_logistics_config()
    order = order_service.get_order_detail_for_seller(order_id, seller_username)
    if not order:
        raise ValueError("Order not found.")

    shipping = order.get("shipping_address") or {}
    suggested_payload = {
        "MerchantID": config["merchant_id"],
        "MerchantOrderNo": f"ORDER-{order_id}",
        "LogisticsType": logistics_type,
        "ReceiverName": shipping.get("recipient", ""),
        "ReceiverPhone": shipping.get("phone", ""),
        "ReceiverAddress": shipping.get("address_line1", ""),
        "ShipmentNote": shipment_note.strip(),
    }
    return {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "order_id": order_id,
        "seller_username": seller_username,
        "logistics_type": logistics_type,
        "callback_url": config["callback_url"],
        "create_url": config["create_url"],
        "status_url": config["status_url"],
        "suggested_payload": suggested_payload,
        "note": "此 payload 為物流 sandbox scaffold，正式上線前需依藍新物流實際 API 文件確認欄位。",
    }


def handle_callback(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    """先保存物流 callback 原始資料，供後續對照官方欄位。"""
    config = _load_logistics_config()
    return {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "merchant_id": config["merchant_id"],
        "received_payload": raw_payload,
        "note": "目前僅做物流 callback 收件示範；正式驗簽與欄位解析待物流 API 規格確認後補上。",
    }
