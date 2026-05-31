"""NewebPay logistics integration helpers.

Responsibilities:
- expose runtime configuration for seller-side logistics testing
- prepare buyer-side convenience-store map form payloads
- persist store-map selections before checkout confirmation
- receive sandbox logistics callbacks for later seller-side inspection
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import os
import secrets
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.utils import timezone

from ..repositories import local_store
from . import orders as order_service

PROVIDER_NAME = "NewebPay Logistics"
MODE_NAME = "sandbox"
DEFAULT_STORE_MAP_URL = "https://ccore.newebpay.com/API/Logistic/storeMap"
DEFAULT_CREATE_URL = "https://ccore.newebpay.com/API/Logistic/createShipment"
DEFAULT_STATUS_URL = "https://ccore.newebpay.com/API/Logistic/queryShipment"
DEFAULT_VERSION = "1.0"
DEFAULT_RESPOND_TYPE = "JSON"
STORE_MAP_SELECTION_TTL_SECONDS = 2 * 60 * 60
STORE_MAP_LGS_TYPE = "B2C"

STORE_BRAND_TO_SHIP_TYPE = {
    "UNIMART": "1",
    "FAMI": "2",
}
STORE_TYPE_TO_BRAND = {
    "1": "UNIMART",
    "2": "FAMI",
    "UNIMART": "UNIMART",
    "FAMI": "FAMI",
}


class NewebpayLogisticsConfigurationError(RuntimeError):
    """Raised when required logistics settings are missing."""


class NewebpayLogisticsDependencyError(RuntimeError):
    """Raised when the crypto dependency is unavailable."""


@dataclass(slots=True)
class NewebpayLogisticsRuntimeConfig:
    merchant_id: str
    hash_key: str
    hash_iv: str
    callback_url: str
    create_url: str
    status_url: str
    store_map_url: str
    store_map_reply_url: str
    store_map_return_url: str
    version: str
    respond_type: str


def _now_timestamp() -> int:
    return int(timezone.now().timestamp())


def _now_iso() -> str:
    return timezone.localtime().isoformat()


def _require_crypto() -> None:
    if not importlib.util.find_spec("Crypto"):
        raise NewebpayLogisticsDependencyError(
            "NewebPay logistics store-map flow requires `pycryptodome` for EncryptData generation."
        )


def _load_crypto():
    _require_crypto()
    from Crypto.Cipher import AES  # type: ignore
    from Crypto.Util.Padding import pad  # type: ignore

    return AES, pad


def _append_query(url: str, values: Dict[str, str]) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params.update({key: value for key, value in values.items() if value != ""})
    return urlunparse(parsed._replace(query=urlencode(params)))


def _derive_store_map_reply_url(callback_url: str) -> str:
    cleaned = callback_url.strip()
    if cleaned.endswith("/api/v1/integrations/newebpay/logistics/sandbox/callback/"):
        return cleaned[: -len("/sandbox/callback/")] + "/store-map/callback/"
    if cleaned.endswith("/api/v1/integrations/newebpay/logistics/callback/"):
        return cleaned[: -len("/callback/")] + "/store-map/callback/"
    return ""


def _default_store_map_return_url() -> str:
    frontend_origin = (os.getenv("STORE_FRONTEND_ORIGIN", "") or "").rstrip("/")
    return f"{frontend_origin}/checkout" if frontend_origin else ""


def _load_runtime_config() -> NewebpayLogisticsRuntimeConfig:
    merchant_id = os.getenv("NEWEBPAY_LOGISTICS_MERCHANT_ID", "").strip() or os.getenv("NEWEBPAY_MERCHANT_ID", "").strip()
    hash_key = os.getenv("NEWEBPAY_LOGISTICS_HASH_KEY", "").strip() or os.getenv("NEWEBPAY_HASH_KEY", "").strip()
    hash_iv = os.getenv("NEWEBPAY_LOGISTICS_HASH_IV", "").strip() or os.getenv("NEWEBPAY_HASH_IV", "").strip()
    callback_url = os.getenv("NEWEBPAY_LOGISTICS_CALLBACK_URL", "").strip()
    create_url = os.getenv("NEWEBPAY_LOGISTICS_CREATE_URL", DEFAULT_CREATE_URL).strip() or DEFAULT_CREATE_URL
    status_url = os.getenv("NEWEBPAY_LOGISTICS_STATUS_URL", DEFAULT_STATUS_URL).strip() or DEFAULT_STATUS_URL
    store_map_url = os.getenv("NEWEBPAY_LOGISTICS_STORE_MAP_URL", DEFAULT_STORE_MAP_URL).strip() or DEFAULT_STORE_MAP_URL
    explicit_reply_url = os.getenv("NEWEBPAY_LOGISTICS_STORE_MAP_REPLY_URL", "").strip()
    store_map_reply_url = explicit_reply_url or _derive_store_map_reply_url(callback_url)
    store_map_return_url = os.getenv("NEWEBPAY_LOGISTICS_STORE_MAP_RETURN_URL", "").strip() or _default_store_map_return_url()
    version = os.getenv("NEWEBPAY_LOGISTICS_VERSION", DEFAULT_VERSION).strip() or DEFAULT_VERSION
    respond_type = os.getenv("NEWEBPAY_LOGISTICS_RESPOND_TYPE", DEFAULT_RESPOND_TYPE).strip() or DEFAULT_RESPOND_TYPE

    missing = [
        name
        for name, value in (
            ("NEWEBPAY_LOGISTICS_MERCHANT_ID / NEWEBPAY_MERCHANT_ID", merchant_id),
            ("NEWEBPAY_LOGISTICS_HASH_KEY / NEWEBPAY_HASH_KEY", hash_key),
            ("NEWEBPAY_LOGISTICS_HASH_IV / NEWEBPAY_HASH_IV", hash_iv),
            ("NEWEBPAY_LOGISTICS_STORE_MAP_REPLY_URL", store_map_reply_url),
            ("NEWEBPAY_LOGISTICS_STORE_MAP_RETURN_URL / STORE_FRONTEND_ORIGIN", store_map_return_url),
        )
        if not value
    ]
    if missing:
        raise NewebpayLogisticsConfigurationError(f"Missing NewebPay logistics settings: {', '.join(missing)}")

    return NewebpayLogisticsRuntimeConfig(
        merchant_id=merchant_id,
        hash_key=hash_key,
        hash_iv=hash_iv,
        callback_url=callback_url,
        create_url=create_url,
        status_url=status_url,
        store_map_url=store_map_url,
        store_map_reply_url=store_map_reply_url,
        store_map_return_url=store_map_return_url,
        version=version,
        respond_type=respond_type,
    )


def _encrypt_payload(plain_text: str, *, hash_key: str, hash_iv: str) -> str:
    AES, pad = _load_crypto()
    cipher = AES.new(hash_key.encode("utf-8"), AES.MODE_CBC, hash_iv.encode("utf-8"))
    encrypted = cipher.encrypt(pad(plain_text.encode("utf-8"), AES.block_size))
    return encrypted.hex()


def _build_hash_data(cipher_hex: str, *, hash_key: str, hash_iv: str) -> str:
    raw = f"HashKey={hash_key}&{cipher_hex}&HashIV={hash_iv}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _mask_secret(value: str, *, head: int = 4, tail: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= head + tail:
        return "*" * len(value)
    return f"{value[:head]}{'*' * max(len(value) - head - tail, 1)}{value[-tail:]}"


def _prune_store_map_selections(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    cutoff = _now_timestamp() - STORE_MAP_SELECTION_TTL_SECONDS
    pruned: list[Dict[str, Any]] = []
    for item in items:
        created_at = str(item.get("created_at") or "")
        try:
            created_ts = int(created_at)
        except (TypeError, ValueError):
            created_ts = 0
        if created_ts and created_ts < cutoff:
            continue
        pruned.append(item)
    return pruned


def _load_store_map_records() -> list[Dict[str, Any]]:
    return _prune_store_map_selections(list(local_store.get_newebpay_store_map_selections()))


def _save_store_map_records(items: list[Dict[str, Any]]) -> None:
    local_store.save_newebpay_store_map_selections(_prune_store_map_selections(items))


def _generate_selection_token(username: str) -> str:
    return f"cvs-{username}-{secrets.token_hex(8)}"


def _generate_merchant_order_no() -> str:
    return f"MAP{_now_timestamp()}{secrets.randbelow(1000):03d}"[:30]


def get_runtime_summary() -> Dict[str, Any]:
    summary = {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "configured": False,
        "missing_settings": [],
        "has_crypto_dependency": bool(importlib.util.find_spec("Crypto")),
    }
    try:
        config = _load_runtime_config()
    except NewebpayLogisticsConfigurationError as exc:
        missing = str(exc).replace("Missing NewebPay logistics settings: ", "")
        summary["missing_settings"] = [item.strip() for item in missing.split(",") if item.strip()]
        return summary

    summary.update(
        {
            "configured": True,
            "merchant_id": config.merchant_id,
            "callback_url": config.callback_url,
            "create_url": config.create_url,
            "status_url": config.status_url,
            "store_map_url": config.store_map_url,
            "store_map_reply_url": config.store_map_reply_url,
            "store_map_return_url": config.store_map_return_url,
        }
    )
    return summary


def prepare_store_map(
    username: str,
    *,
    pickup_store_brand: str,
    payment_method: str = "",
    return_url: str = "",
) -> Dict[str, Any]:
    config = _load_runtime_config()
    brand = pickup_store_brand.strip().upper()
    ship_type = STORE_BRAND_TO_SHIP_TYPE.get(brand)
    if not ship_type:
        raise ValueError("Unsupported convenience-store brand.")

    selection_token = _generate_selection_token(username)
    merchant_order_no = _generate_merchant_order_no()
    base_return_url = return_url.strip() or config.store_map_return_url
    resolved_return_url = _append_query(
        base_return_url,
        {
            "store_map_token": selection_token,
            "store_map": "return",
        },
    )
    timestamp = _now_timestamp()
    normalized_payment_method = payment_method.strip().lower()
    is_collection = "Y" if normalized_payment_method in {"convenience_store_cod", "cod", "pickup_cod"} else "N"

    plain_params = {
        "MerchantID": config.merchant_id,
        "MerchantOrderNo": merchant_order_no,
        "LgsType": STORE_MAP_LGS_TYPE,
        "ShipType": ship_type,
        "IsCollection": is_collection,
        "ServerReplyURL": config.store_map_reply_url,
        "ReturnURL": resolved_return_url,
        "TimeStamp": str(timestamp),
        "ExtraData": selection_token,
    }
    cipher_hex = _encrypt_payload(urlencode(plain_params), hash_key=config.hash_key, hash_iv=config.hash_iv)
    hash_data = _build_hash_data(cipher_hex, hash_key=config.hash_key, hash_iv=config.hash_iv)

    prepared = {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "selection_token": selection_token,
        "buyer_username": username,
        "pickup_store_brand": brand,
        "pickup_store_brand_label": order_service.CONVENIENCE_STORE_BRAND_LABELS.get(brand, brand),
        "payment_method": payment_method.strip(),
        "merchant_order_no": merchant_order_no,
        "action_url": config.store_map_url,
        "form_method": "POST",
        "callback_url": config.store_map_reply_url,
        "return_url": resolved_return_url,
        "plain_params": plain_params,
        "form_fields": {
            "MerchantID_": config.merchant_id,
            "PostData_": cipher_hex,
            "UID_": config.merchant_id,
            "Version_": config.version,
            "RespondType_": config.respond_type,
            "EncryptData_": cipher_hex,
            "HashData_": hash_data,
        },
        "note": "Submit form_fields to NewebPay storeMap to let the buyer choose a pickup store.",
    }
    return prepared


def build_store_map_debug_payload(
    username: str,
    *,
    pickup_store_brand: str,
    payment_method: str = "",
    return_url: str = "",
) -> Dict[str, Any]:
    config = _load_runtime_config()
    prepared = prepare_store_map(
        username,
        pickup_store_brand=pickup_store_brand,
        payment_method=payment_method,
        return_url=return_url,
    )
    form_fields = dict(prepared["form_fields"])
    plain_params = dict(prepared["plain_params"])
    return {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "runtime": {
            "merchant_id": config.merchant_id,
            "hash_key_length": len(config.hash_key),
            "hash_iv_length": len(config.hash_iv),
            "hash_key_preview": _mask_secret(config.hash_key),
            "hash_iv_preview": _mask_secret(config.hash_iv),
            "store_map_url": config.store_map_url,
            "store_map_reply_url": config.store_map_reply_url,
            "store_map_return_url": config.store_map_return_url,
            "version": config.version,
            "respond_type": config.respond_type,
        },
        "prepared": {
            "selection_token": prepared["selection_token"],
            "merchant_order_no": prepared["merchant_order_no"],
            "pickup_store_brand": prepared["pickup_store_brand"],
            "pickup_store_brand_label": prepared["pickup_store_brand_label"],
            "payment_method": prepared["payment_method"],
            "action_url": prepared["action_url"],
            "callback_url": prepared["callback_url"],
            "return_url": prepared["return_url"],
            "plain_params": plain_params,
            "plain_params_encoded": urlencode(plain_params),
            "form_fields": form_fields,
        },
        "checks": {
            "has_merchant_id_field": bool(form_fields.get("MerchantID_")),
            "has_post_data_field": bool(form_fields.get("PostData_")),
            "has_encrypt_data_field": bool(form_fields.get("EncryptData_")),
            "has_hash_data_field": bool(form_fields.get("HashData_")),
            "merchant_id_matches_uid": form_fields.get("MerchantID_") == form_fields.get("UID_"),
            "post_data_matches_encrypt_data": form_fields.get("PostData_") == form_fields.get("EncryptData_"),
            "merchant_id_in_plain_params": plain_params.get("MerchantID") == config.merchant_id,
        },
    }


def persist_store_map_prepare(prepared: Dict[str, Any]) -> Dict[str, Any]:
    records = _load_store_map_records()
    token = str(prepared["selection_token"])
    record = next((item for item in records if item.get("selection_token") == token), None)
    now_ts = str(_now_timestamp())
    now_iso = _now_iso()
    if record is None:
        record = {
            "selection_token": token,
            "buyer_username": str(prepared["buyer_username"]),
            "pickup_store_brand": str(prepared["pickup_store_brand"]),
            "pickup_store_brand_label": str(prepared.get("pickup_store_brand_label", "")),
            "payment_method": str(prepared.get("payment_method", "")),
            "merchant_order_no": str(prepared["merchant_order_no"]),
            "status": "pending",
            "store_id": "",
            "store_name": "",
            "store_address": "",
            "store_type": "",
            "created_at": now_ts,
            "created_at_iso": now_iso,
            "updated_at": now_ts,
            "updated_at_iso": now_iso,
            "reply_payload": {},
            "return_url": str(prepared["return_url"]),
            "callback_url": str(prepared["callback_url"]),
        }
        records.append(record)
    else:
        record.update(
            {
                "buyer_username": str(prepared["buyer_username"]),
                "pickup_store_brand": str(prepared["pickup_store_brand"]),
                "pickup_store_brand_label": str(prepared.get("pickup_store_brand_label", "")),
                "payment_method": str(prepared.get("payment_method", "")),
                "merchant_order_no": str(prepared["merchant_order_no"]),
                "status": "pending",
                "updated_at": now_ts,
                "updated_at_iso": now_iso,
                "return_url": str(prepared["return_url"]),
                "callback_url": str(prepared["callback_url"]),
            }
        )
    _save_store_map_records(records)
    return dict(record)


def handle_store_map_callback(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    _load_runtime_config()
    records = _load_store_map_records()
    selection_token = str(raw_payload.get("ExtraData", "")).strip()
    merchant_order_no = str(raw_payload.get("MerchantOrderNo", "")).strip()
    record = next(
        (
            item
            for item in records
            if (selection_token and item.get("selection_token") == selection_token)
            or (merchant_order_no and item.get("merchant_order_no") == merchant_order_no)
        ),
        None,
    )
    if record is None:
        raise ValueError("Store-map selection session not found.")

    store_type = str(raw_payload.get("StoreType", "")).strip().upper()
    pickup_store_brand = STORE_TYPE_TO_BRAND.get(store_type, str(record.get("pickup_store_brand", "")).upper())
    status_value = str(raw_payload.get("Status", "")).strip().upper()
    is_ready = bool(raw_payload.get("StoreID")) and status_value not in {"FAILED", "ERROR"}
    now_ts = str(_now_timestamp())
    now_iso = _now_iso()

    record.update(
        {
            "pickup_store_brand": pickup_store_brand,
            "pickup_store_brand_label": order_service.CONVENIENCE_STORE_BRAND_LABELS.get(pickup_store_brand, pickup_store_brand),
            "status": "selected" if is_ready else "pending",
            "store_id": str(raw_payload.get("StoreID", "")).strip(),
            "store_name": str(raw_payload.get("StoreName", "")).strip(),
            "store_address": str(raw_payload.get("StoreAddr", "")).strip(),
            "store_type": store_type,
            "updated_at": now_ts,
            "updated_at_iso": now_iso,
            "reply_payload": dict(raw_payload),
        }
    )
    _save_store_map_records(records)
    return {
        "selection_token": record["selection_token"],
        "merchant_order_no": record["merchant_order_no"],
        "status": record["status"],
        "pickup_store_brand": record["pickup_store_brand"],
        "pickup_store_brand_label": record["pickup_store_brand_label"],
        "store_id": record["store_id"],
        "store_name": record["store_name"],
        "store_address": record["store_address"],
        "reply_payload": dict(raw_payload),
    }


def get_store_selection(selection_token: str, username: str) -> Optional[Dict[str, Any]]:
    token = selection_token.strip()
    if not token:
        return None
    record = next((item for item in _load_store_map_records() if item.get("selection_token") == token), None)
    if record is None or str(record.get("buyer_username", "")) != username:
        return None
    return {
        "selection_token": token,
        "status": str(record.get("status", "pending")),
        "is_ready": str(record.get("status", "")) == "selected",
        "pickup_store_brand": str(record.get("pickup_store_brand", "")),
        "pickup_store_brand_label": str(record.get("pickup_store_brand_label", "")),
        "pickup_store_code": str(record.get("store_id", "")),
        "pickup_store_name": str(record.get("store_name", "")),
        "pickup_store_address": str(record.get("store_address", "")),
        "merchant_order_no": str(record.get("merchant_order_no", "")),
        "updated_at": str(record.get("updated_at_iso", "")),
    }


def prepare_logistics_request(
    order_id: int,
    seller_username: str,
    *,
    logistics_type: str = "UNIMARTC2C",
    shipment_note: str = "",
) -> Dict[str, Any]:
    config = _load_runtime_config()
    order = order_service.get_order_detail_for_seller(order_id, seller_username)
    if not order:
        raise ValueError("Order not found.")

    shipping = order.get("shipping_address") or {}
    suggested_payload = {
        "MerchantID": config.merchant_id,
        "MerchantOrderNo": f"ORDER-{order_id}",
        "LogisticsType": logistics_type,
        "ReceiverName": shipping.get("recipient", ""),
        "ReceiverPhone": shipping.get("phone", ""),
        "ReceiverAddress": shipping.get("address_line", ""),
        "ShippingMethod": order.get("shipping_method", ""),
        "PaymentMethod": order.get("payment_method", ""),
        "CVSStoreBrand": order.get("pickup_store_brand", ""),
        "CVSStoreCode": order.get("pickup_store_code", ""),
        "CVSStoreName": order.get("pickup_store_name", ""),
        "CVSStoreAddress": order.get("pickup_store_address", ""),
        "ShipmentNote": shipment_note.strip(),
    }
    return {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "order_id": order_id,
        "seller_username": seller_username,
        "logistics_type": logistics_type,
        "callback_url": config.callback_url,
        "create_url": config.create_url,
        "status_url": config.status_url,
        "suggested_payload": suggested_payload,
        "buyer_shipping_summary": {
            "shipping_method": order.get("shipping_method", ""),
            "shipping_method_label": order.get("shipping_method_label", ""),
            "payment_method": order.get("payment_method", ""),
            "payment_method_label": order.get("payment_method_label", ""),
            "pickup_store_brand": order.get("pickup_store_brand", ""),
            "pickup_store_brand_label": order.get("pickup_store_brand_label", ""),
            "pickup_store_code": order.get("pickup_store_code", ""),
            "pickup_store_name": order.get("pickup_store_name", ""),
            "pickup_store_address": order.get("pickup_store_address", ""),
            "is_convenience_store": order.get("shipping_method") == order_service.SHIPPING_METHOD_CONVENIENCE_STORE,
        },
        "note": "Seller-side scaffold only: inspect payload before connecting the real createShipment API.",
    }


def persist_prepared_attempt(prepared: Dict[str, Any]) -> Dict[str, Any]:
    logs = list(local_store.get_newebpay_logistics_logs())
    suggested = dict(prepared.get("suggested_payload") or {})
    merchant_order_no = str(suggested.get("MerchantOrderNo", "")).strip()
    order_id = int(prepared["order_id"])
    seller_username = str(prepared["seller_username"])
    now = _now_iso()

    existing = next((item for item in logs if merchant_order_no and item.get("merchant_order_no") == merchant_order_no), None)
    if existing is None:
        existing = {
            "provider": PROVIDER_NAME,
            "mode": MODE_NAME,
            "order_id": order_id,
            "seller_username": seller_username,
            "merchant_order_no": merchant_order_no,
            "logistics_no": "",
            "status": "created",
            "status_label": "Scaffold payload prepared",
            "store_type": prepared.get("logistics_type", ""),
            "temperature": "normal",
            "receiver_name": suggested.get("ReceiverName", ""),
            "receiver_phone": suggested.get("ReceiverPhone", ""),
            "shipment_note": suggested.get("ShipmentNote", ""),
            "created_at": now,
            "updated_at": now,
            "callback_count": 0,
            "raw_payload": {
                "prepared_payload": suggested,
            },
        }
        logs.append(existing)
    else:
        existing["updated_at"] = now
        existing["store_type"] = prepared.get("logistics_type", "")
        existing["shipment_note"] = suggested.get("ShipmentNote", "")
        existing["raw_payload"] = {"prepared_payload": suggested}

    local_store.save_newebpay_logistics_logs(logs)
    return dict(existing)


def handle_callback(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    config = _load_runtime_config()
    merchant_order_no = str(raw_payload.get("MerchantOrderNo", "")).strip()
    logistics_no = str(raw_payload.get("LogisticsID", "")).strip()
    status_value = str(raw_payload.get("Status", "")).strip()
    message = str(raw_payload.get("Message", "")).strip()

    raw_id = merchant_order_no.replace("ORDER-", "", 1) if merchant_order_no.startswith("ORDER-") else ""
    order_id = int(raw_id) if raw_id.isdigit() else None
    seller_username = ""
    if order_id is not None:
        order = local_store.get_order_by_id(order_id)
        if order:
            first_item = (order.get("items") or [{}])[0]
            seller_username = str(first_item.get("seller_username", "")).strip()

    normalized_status = {
        "": "created",
        "SUCCESS": "picked_up",
        "CREATED": "created",
        "PICKED_UP": "picked_up",
        "DELIVERED": "delivered",
        "FAILED": "failed",
    }.get(status_value.upper(), "created")
    status_label = {
        "created": "Created",
        "picked_up": "Picked up / in transit",
        "delivered": "Delivered",
        "failed": f"Failed / {status_value or 'UNKNOWN'}",
    }[normalized_status]

    logs = list(local_store.get_newebpay_logistics_logs())
    existing = next(
        (
            item
            for item in logs
            if (merchant_order_no and item.get("merchant_order_no") == merchant_order_no)
            or (logistics_no and item.get("logistics_no") == logistics_no)
        ),
        None,
    )
    now = _now_iso()
    if existing is None:
        existing = {
            "provider": PROVIDER_NAME,
            "mode": MODE_NAME,
            "order_id": order_id or 0,
            "seller_username": seller_username,
            "merchant_order_no": merchant_order_no,
            "logistics_no": logistics_no,
            "status": normalized_status,
            "status_label": status_label,
            "store_type": "",
            "temperature": "normal",
            "receiver_name": "",
            "receiver_phone": "",
            "shipment_note": message,
            "created_at": now,
            "updated_at": now,
            "callback_count": 1,
            "raw_payload": raw_payload,
        }
        logs.append(existing)
    else:
        existing["logistics_no"] = logistics_no or existing.get("logistics_no", "")
        existing["status"] = normalized_status
        existing["status_label"] = status_label
        if message:
            existing["shipment_note"] = message
        existing["updated_at"] = now
        existing["callback_count"] = int(existing.get("callback_count", 0)) + 1
        existing["raw_payload"] = raw_payload

    local_store.save_newebpay_logistics_logs(logs)
    return {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "merchant_id": config.merchant_id,
        "record": dict(existing),
        "received_payload": raw_payload,
        "note": "Sandbox logistics callback recorded for seller-side inspection.",
    }
