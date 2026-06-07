"""藍新超商店到店選店流程服務。

這支 service 負責：
- 讀取藍新物流 store-map 所需的 runtime 設定
- 組出前端自動送出的選店 form payload
- 保存與查詢 checkout 用的超商門市選擇結果
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import secrets
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.utils import timezone

from ..models import AppUser as AppUserModel
from ..models import NewebpayStoreMapSelection as NewebpayStoreMapSelectionModel
from ..repositories import local_store
from . import orders as order_service

PROVIDER_NAME = "NewebPay Store Map"
MODE_NAME = "sandbox"
DEFAULT_STORE_MAP_URL = "https://ccore.newebpay.com/API/Logistic/storeMap"
DEFAULT_VERSION = "1.0"
DEFAULT_RESPOND_TYPE = "JSON"
STORE_MAP_SELECTION_TTL_SECONDS = 2 * 60 * 60
STORE_MAP_LGS_TYPE = "B2C"

HARDCODED_LOGISTICS_DEBUG_CREDENTIALS: Dict[str, str] = {}

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
    """Raised when required store-map settings are missing."""


class NewebpayLogisticsDependencyError(RuntimeError):
    """Raised when the crypto dependency is unavailable."""


@dataclass(slots=True)
class NewebpayLogisticsRuntimeConfig:
    merchant_id: str
    hash_key: str
    hash_iv: str
    store_map_url: str
    store_map_reply_url: str
    store_map_return_url: str
    version: str
    respond_type: str
    credentials_source: str = "env"


def _now_timestamp() -> int:
    return int(timezone.now().timestamp())


def _now_iso() -> str:
    return timezone.localtime().isoformat()


def _require_crypto() -> None:
    if not importlib.util.find_spec("Crypto"):
        raise NewebpayLogisticsDependencyError(
            "NewebPay store-map flow requires `pycryptodome` for EncryptData generation."
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


def _replace_path(url: str, path: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=path, params="", query="", fragment=""))


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


def _build_store_map_gateway_return_url(reply_url: str, selection_token: str) -> str:
    return _replace_path(reply_url, f"/sm/{selection_token}/")


def _load_runtime_config() -> NewebpayLogisticsRuntimeConfig:
    # 選店流程的 MerchantID / HashKey / 回呼網址集中在這裡組裝，
    # 讓 prepare / callback / debug 都讀同一份設定。
    hardcoded_merchant_id = str(HARDCODED_LOGISTICS_DEBUG_CREDENTIALS.get("merchant_id", "")).strip()
    hardcoded_hash_key = str(HARDCODED_LOGISTICS_DEBUG_CREDENTIALS.get("hash_key", "")).strip()
    hardcoded_hash_iv = str(HARDCODED_LOGISTICS_DEBUG_CREDENTIALS.get("hash_iv", "")).strip()
    credentials_source = "hardcoded_debug_override" if hardcoded_merchant_id and hardcoded_hash_key and hardcoded_hash_iv else "env"

    merchant_id = hardcoded_merchant_id or os.getenv("NEWEBPAY_LOGISTICS_MERCHANT_ID", "").strip() or os.getenv("NEWEBPAY_MERCHANT_ID", "").strip()
    hash_key = hardcoded_hash_key or os.getenv("NEWEBPAY_LOGISTICS_HASH_KEY", "").strip() or os.getenv("NEWEBPAY_HASH_KEY", "").strip()
    hash_iv = hardcoded_hash_iv or os.getenv("NEWEBPAY_LOGISTICS_HASH_IV", "").strip() or os.getenv("NEWEBPAY_HASH_IV", "").strip()
    callback_url = os.getenv("NEWEBPAY_LOGISTICS_CALLBACK_URL", "").strip()
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
        raise NewebpayLogisticsConfigurationError(f"Missing NewebPay store-map settings: {', '.join(missing)}")

    return NewebpayLogisticsRuntimeConfig(
        merchant_id=merchant_id,
        hash_key=hash_key,
        hash_iv=hash_iv,
        store_map_url=store_map_url,
        store_map_reply_url=store_map_reply_url,
        store_map_return_url=store_map_return_url,
        version=version,
        respond_type=respond_type,
        credentials_source=credentials_source,
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
    # 選店 token 只需要短暫存活，避免過期資料一直堆在 JSON fallback。
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


def _db_store_map_enabled() -> bool:
    try:
        NewebpayStoreMapSelectionModel.objects.count()
        return True
    except Exception:
        return False


def _ensure_db_buyer(username: str) -> Optional[AppUserModel]:
    # ORM 表存在時，補一份 buyer 關聯，讓後續 checkout / 訂單可以直接串起來。
    cleaned = username.strip()
    if not cleaned:
        return None
    user = AppUserModel.objects.filter(username=cleaned).first()
    if user:
        return user
    snapshot = local_store.get_user_by_username(cleaned)
    if not snapshot:
        return None
    email = str(snapshot.get("email") or "").strip() or f"{cleaned}@seed.local"
    user, _ = AppUserModel.objects.get_or_create(
        username=cleaned,
        defaults={
            "email": email,
            "password_hash": str(snapshot.get("password_hash") or ""),
            "display_name": str(snapshot.get("display_name") or cleaned),
            "role": str(snapshot.get("role") or "member"),
            "account_status": str(snapshot.get("account_status") or "active"),
            "seller_request_status": str(snapshot.get("seller_request_status") or "none"),
        },
    )
    return user


def _record_from_model(record: NewebpayStoreMapSelectionModel) -> Dict[str, Any]:
    # 將 ORM record 壓成前端與 legacy local_store 都能共用的 canonical payload。
    created_at_ts = str(int(record.created_at.timestamp())) if record.created_at else "0"
    updated_at_ts = str(int(record.updated_at.timestamp())) if record.updated_at else created_at_ts
    return {
        "selection_token": record.selection_token,
        "buyer_username": record.buyer_username_snapshot or (record.buyer.username if record.buyer else ""),
        "pickup_store_brand": record.pickup_store_brand,
        "pickup_store_brand_label": record.pickup_store_brand_label,
        "payment_method": record.payment_method,
        "merchant_order_no": record.merchant_order_no,
        "status": record.status,
        "store_id": record.store_id,
        "store_name": record.store_name,
        "store_address": record.store_address,
        "store_type": record.store_type,
        "created_at": created_at_ts,
        "created_at_iso": timezone.localtime(record.created_at).isoformat() if record.created_at else "",
        "updated_at": updated_at_ts,
        "updated_at_iso": timezone.localtime(record.updated_at).isoformat() if record.updated_at else "",
        "reply_payload": dict(record.reply_payload or {}),
        "return_url": record.return_url,
        "gateway_return_url": record.gateway_return_url,
        "callback_url": record.callback_url,
        "action_url": record.action_url,
        "plain_params": dict(record.plain_params or {}),
        "form_fields": dict(record.form_fields or {}),
    }


def _sync_local_store_map_record(record: Dict[str, Any]) -> None:
    # 即使已經切到 ORM，也同步回 local JSON，維持舊 API / debug 工具的可讀性。
    if _db_store_map_enabled():
        return
    records = _load_store_map_records()
    token = str(record.get("selection_token") or "")
    existing = next((item for item in records if item.get("selection_token") == token), None)
    if existing is None:
        records.append(dict(record))
    else:
        existing.update(dict(record))
    _save_store_map_records(records)


def _get_db_store_map_record_by_token(selection_token: str) -> Optional[NewebpayStoreMapSelectionModel]:
    token = selection_token.strip()
    if not token or not _db_store_map_enabled():
        return None
    return NewebpayStoreMapSelectionModel.objects.filter(selection_token=token).first()


def _get_db_store_map_record(selection_token: str, merchant_order_no: str) -> Optional[NewebpayStoreMapSelectionModel]:
    if not _db_store_map_enabled():
        return None
    token = selection_token.strip()
    order_no = merchant_order_no.strip()
    queryset = NewebpayStoreMapSelectionModel.objects.all()
    if token:
        record = queryset.filter(selection_token=token).first()
        if record:
            return record
    if order_no:
        return queryset.filter(merchant_order_no=order_no).order_by("-updated_at", "-id").first()
    return None


def _load_store_map_records() -> list[Dict[str, Any]]:
    return _prune_store_map_selections(list(local_store.get_newebpay_store_map_selections()))


def _save_store_map_records(items: list[Dict[str, Any]]) -> None:
    if _db_store_map_enabled():
        return
    local_store.save_newebpay_store_map_selections(_prune_store_map_selections(items))


def _generate_selection_token(username: str) -> str:
    return secrets.token_hex(5)


def _generate_merchant_order_no() -> str:
    return f"MAP{_now_timestamp()}{secrets.randbelow(1000):03d}"[:30]


def get_runtime_summary() -> Dict[str, Any]:
    # 提供給 debug API 看目前憑證、回呼網址和 Crypto 依賴是否就緒。
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
        missing = str(exc).replace("Missing NewebPay store-map settings: ", "")
        summary["missing_settings"] = [item.strip() for item in missing.split(",") if item.strip()]
        return summary

    summary.update(
        {
            "configured": True,
            "merchant_id": config.merchant_id,
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
    # 這個 payload 會被前端轉成 auto-submit form，實際帶使用者跳去藍新選店頁。
    config = _load_runtime_config()
    brand = pickup_store_brand.strip().upper()
    ship_type = STORE_BRAND_TO_SHIP_TYPE.get(brand)
    if not ship_type:
        raise ValueError("Unsupported convenience-store brand.")

    selection_token = _generate_selection_token(username)
    merchant_order_no = _generate_merchant_order_no()
    base_return_url = return_url.strip() or config.store_map_return_url
    client_return_url = _append_query(base_return_url, {"store_map_token": selection_token})
    gateway_return_url = _build_store_map_gateway_return_url(config.store_map_reply_url, selection_token)
    normalized_payment_method = payment_method.strip().lower()
    is_collection = "Y" if normalized_payment_method in {"convenience_store_cod", "cod", "pickup_cod"} else "N"

    # 藍新物流要求的原始欄位先組成明文，再加密成 PostData / EncryptData。
    plain_params = {
        "MerchantID": config.merchant_id,
        "MerchantOrderNo": merchant_order_no,
        "LgsType": STORE_MAP_LGS_TYPE,
        "ShipType": ship_type,
        "IsCollection": is_collection,
        "ServerReplyURL": config.store_map_reply_url,
        "ReturnURL": gateway_return_url,
        "TimeStamp": str(_now_timestamp()),
        "ExtraData": selection_token,
    }
    cipher_hex = _encrypt_payload(urlencode(plain_params), hash_key=config.hash_key, hash_iv=config.hash_iv)
    hash_data = _build_hash_data(cipher_hex, hash_key=config.hash_key, hash_iv=config.hash_iv)

    return {
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
        "return_url": client_return_url,
        "gateway_return_url": gateway_return_url,
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


def build_store_map_debug_payload(
    username: str,
    *,
    pickup_store_brand: str,
    payment_method: str = "",
    return_url: str = "",
) -> Dict[str, Any]:
    # debug payload 會把 runtime 與 prepare 結果攤平，方便直接檢查欄位是否對上藍新規格。
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
            "credentials_source": config.credentials_source,
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
    # prepare 階段先把 token 與 callback 所需上下文存起來，之後藍新回呼才能找回原 session。
    if _db_store_map_enabled():
        token = str(prepared["selection_token"])
        buyer_username = str(prepared["buyer_username"])
        buyer = _ensure_db_buyer(buyer_username)
        record, created = NewebpayStoreMapSelectionModel.objects.get_or_create(
            selection_token=token,
            defaults={
                "buyer": buyer,
                "buyer_username_snapshot": buyer_username,
                "pickup_store_brand": str(prepared["pickup_store_brand"]),
                "pickup_store_brand_label": str(prepared.get("pickup_store_brand_label", "")),
                "payment_method": str(prepared.get("payment_method", "")),
                "merchant_order_no": str(prepared["merchant_order_no"]),
                "status": "pending",
                "return_url": str(prepared["return_url"]),
                "gateway_return_url": str(prepared.get("gateway_return_url", "")),
                "callback_url": str(prepared["callback_url"]),
                "action_url": str(prepared.get("action_url", "")),
                "plain_params": dict(prepared.get("plain_params") or {}),
                "form_fields": dict(prepared.get("form_fields") or {}),
            },
        )
        if not created:
            record.buyer = buyer
            record.buyer_username_snapshot = buyer_username
            record.pickup_store_brand = str(prepared["pickup_store_brand"])
            record.pickup_store_brand_label = str(prepared.get("pickup_store_brand_label", ""))
            record.payment_method = str(prepared.get("payment_method", ""))
            record.merchant_order_no = str(prepared["merchant_order_no"])
            record.status = "pending"
            record.return_url = str(prepared["return_url"])
            record.gateway_return_url = str(prepared.get("gateway_return_url", ""))
            record.callback_url = str(prepared["callback_url"])
            record.action_url = str(prepared.get("action_url", ""))
            record.plain_params = dict(prepared.get("plain_params") or {})
            record.form_fields = dict(prepared.get("form_fields") or {})
            record.save()
        payload = _record_from_model(record)
        _sync_local_store_map_record(payload)
        return payload

    # ORM 尚未可用時，退回 JSON bucket 保存同一份資料結構。
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
            "gateway_return_url": str(prepared.get("gateway_return_url", "")),
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
                "gateway_return_url": str(prepared.get("gateway_return_url", "")),
                "callback_url": str(prepared["callback_url"]),
            }
        )
    _save_store_map_records(records)
    return dict(record)


def handle_store_map_callback(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    # 藍新回來後，根據 ExtraData / MerchantOrderNo 把選中的門市寫回待結帳紀錄。
    _load_runtime_config()
    selection_token = str(raw_payload.get("ExtraData", "")).strip()
    merchant_order_no = str(raw_payload.get("MerchantOrderNo", "")).strip()
    if _db_store_map_enabled():
        record = _get_db_store_map_record(selection_token, merchant_order_no)
        if record is None:
            raise ValueError("Store-map selection session not found.")

        # callback payload 會提供實際門市資訊，這裡把品牌 / 狀態標準化成 checkout 可直接吃的欄位。
        store_type = str(raw_payload.get("StoreType", "")).strip().upper()
        pickup_store_brand = STORE_TYPE_TO_BRAND.get(store_type, str(record.pickup_store_brand or "").upper())
        status_value = str(raw_payload.get("Status", "")).strip().upper()
        is_ready = bool(raw_payload.get("StoreID")) and status_value not in {"FAILED", "ERROR"}
        record.pickup_store_brand = pickup_store_brand
        record.pickup_store_brand_label = order_service.CONVENIENCE_STORE_BRAND_LABELS.get(
            pickup_store_brand,
            pickup_store_brand,
        )
        record.status = "selected" if is_ready else "pending"
        record.store_id = str(raw_payload.get("StoreID", "")).strip()
        record.store_name = str(raw_payload.get("StoreName", "")).strip()
        record.store_address = str(raw_payload.get("StoreAddr", "")).strip()
        record.store_type = store_type
        record.reply_payload = dict(raw_payload)
        record.save()
        legacy = _record_from_model(record)
        _sync_local_store_map_record(legacy)
        return {
            "selection_token": legacy["selection_token"],
            "merchant_order_no": legacy["merchant_order_no"],
            "status": legacy["status"],
            "pickup_store_brand": legacy["pickup_store_brand"],
            "pickup_store_brand_label": legacy["pickup_store_brand_label"],
            "store_id": legacy["store_id"],
            "store_name": legacy["store_name"],
            "store_address": legacy["store_address"],
            "reply_payload": dict(raw_payload),
        }

    records = _load_store_map_records()
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

    # JSON fallback 與 ORM 版保持相同欄位語意，避免前端讀取邏輯分叉。
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
    # checkout 前端用 token 輪詢或重取選店結果，只允許原 buyer 讀自己的門市資料。
    token = selection_token.strip()
    if not token:
        return None
    if _db_store_map_enabled():
        record = _get_db_store_map_record_by_token(token)
        if record is not None:
            record_username = record.buyer_username_snapshot or (record.buyer.username if record.buyer else "")
            if record_username != username:
                return None
            return {
                "selection_token": token,
                "status": record.status,
                "is_ready": record.status == "selected",
                "pickup_store_brand": record.pickup_store_brand,
                "pickup_store_brand_label": record.pickup_store_brand_label,
                "pickup_store_code": record.store_id,
                "pickup_store_name": record.store_name,
                "pickup_store_address": record.store_address,
                "merchant_order_no": record.merchant_order_no,
                "updated_at": timezone.localtime(record.updated_at).isoformat() if record.updated_at else "",
            }
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


def get_store_map_client_return_url(selection_token: str) -> str:
    # 藍新選店完成後，瀏覽器要導回哪個頁面，優先取 prepare 時保存的 return_url。
    token = selection_token.strip()
    if not token:
        return _default_store_map_return_url()
    if _db_store_map_enabled():
        record = _get_db_store_map_record_by_token(token)
        if record is not None:
            return record.return_url or _default_store_map_return_url()
    record = next((item for item in _load_store_map_records() if item.get("selection_token") == token), None)
    if record is None:
        return _default_store_map_return_url()
    return str(record.get("return_url") or _default_store_map_return_url())
