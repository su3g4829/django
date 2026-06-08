"""藍新金流 sandbox 支付服務。

這支 service 負責：
- 讀取 MerchantID / HashKey / HashIV 等 runtime 設定
- 組出 checkout 要送去藍新 MPG 的 form-post payload
- 驗證 callback 的 TradeSha 並解出 TradeInfo
- 將 prepare / callback / query 結果保存成 ORM 或 local JSON 紀錄
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import logging
import os
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
from urllib.parse import parse_qsl, urlencode
from urllib.request import Request, urlopen

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..models import Order as OrderModel
from ..models import PaymentCallbackLog as PaymentCallbackLogModel
from ..models import PaymentSource as PaymentSourceModel
from ..models import PaymentStatus as PaymentStatusModel
from ..models import PaymentTransaction as PaymentTransactionModel
from ..repositories import local_store
from . import orders as order_service

logger = logging.getLogger(__name__)

PROVIDER_NAME = "NewebPay Payment"
MODE_NAME = "sandbox"
DEFAULT_GATEWAY_URL = "https://ccore.newebpay.com/MPG/mpg_gateway"
DEFAULT_QUERY_URL = "https://ccore.newebpay.com/API/QueryTradeInfo"
DEFAULT_VERSION = "2.2"
DEFAULT_RESPOND_TYPE = "JSON"
DEFAULT_QUERY_VERSION = "1.3"
MERCHANT_ORDER_PREFIX = "ORDER"
DEFAULT_PAYMENT_FLAG_VALUES = {
    "CREDIT": 0,
    "WEBATM": 1,
    "VACC": 1,
    "CVS": 1,
    "BARCODE": 1,
    "ANDROIDPAY": 0,
    "SAMSUNGPAY": 0,
}
PAYMENT_FLAG_ENV_MAP = {
    "CREDIT": "NEWEBPAY_ENABLE_CREDIT",
    "WEBATM": "NEWEBPAY_ENABLE_WEBATM",
    "VACC": "NEWEBPAY_ENABLE_VACC",
    "CVS": "NEWEBPAY_ENABLE_CVS",
    "BARCODE": "NEWEBPAY_ENABLE_BARCODE",
    "ANDROIDPAY": "NEWEBPAY_ENABLE_ANDROIDPAY",
    "SAMSUNGPAY": "NEWEBPAY_ENABLE_SAMSUNGPAY",
}
STORE_TYPE_TO_BRAND = {
    "7-ELEVEN": "UNIMART",
    "UNIMART": "UNIMART",
    "FAMILY": "FAMI",
    "FAMI": "FAMI",
    "全家": "FAMI",
}


def _db_payments_enabled() -> bool:
    """Return whether payment ORM tables are available for read/write."""
    # 新版 payment tables 存在時優先走 ORM；否則退回 local_store 的 JSON log。
    try:
        PaymentTransactionModel.objects.count()
        PaymentCallbackLogModel.objects.count()
        return True
    except Exception:
        return False


def _iso_or_empty(value: Any) -> str:
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return timezone.localtime(value).isoformat()
    return str(value)


def _aware_datetime_or_none(value: str) -> Any:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    parsed = parse_datetime(cleaned)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _payment_status_label(status: str, source: str = "") -> str:
    if source == PaymentSourceModel.PREPARE and status == PaymentStatusModel.PENDING:
        return "已建立 sandbox payload"
    return order_service.PAYMENT_STATUS_LABELS.get(status, status)


def _payment_note(source: str) -> str:
    return {
        PaymentSourceModel.PREPARE: "sandbox prepare",
        PaymentSourceModel.CALLBACK: "sandbox callback",
        PaymentSourceModel.RETURN: "sandbox return",
        PaymentSourceModel.QUERY: "sandbox query",
        PaymentSourceModel.MANUAL: "sandbox manual",
    }.get(source, "")


def _event_record_from_callback_log(log: PaymentCallbackLogModel) -> Dict[str, Any]:
    payload = dict(log.parsed_payload or log.raw_payload or {})
    payload["source"] = log.source
    payload["is_success"] = bool(log.is_success)
    payload["http_status"] = int(log.http_status)
    payload["note"] = log.note
    payload["created_at"] = _iso_or_empty(log.created_at)
    return payload


def _raw_payload_from_transaction(record: PaymentTransactionModel) -> Dict[str, Any]:
    # 把 prepare 時的表單欄位、callback 事件、query 診斷整合成單一 raw payload，
    # 方便 debug API 一次看完整支付歷程。
    latest_raw_payload = dict(record.latest_raw_payload or {})
    raw_payload: Dict[str, Any] = {
        **latest_raw_payload,
        "prepared_form_fields": dict(record.prepared_form_fields or {}),
        "prepared_trade_info_params": dict(record.prepared_trade_info_params or {}),
        "events": [_event_record_from_callback_log(log) for log in record.callback_logs.order_by("id")],
    }
    if record.last_query_amount:
        raw_payload["last_query_amount"] = record.last_query_amount
    if record.last_query_merchant_order_no:
        raw_payload["last_query_merchant_order_no"] = record.last_query_merchant_order_no
    if record.last_query_error:
        raw_payload["last_query_error"] = record.last_query_error
    if record.last_query_response:
        raw_payload["last_query_response"] = record.last_query_response
    if record.last_query_at:
        raw_payload["last_query_at"] = _iso_or_empty(record.last_query_at)
    return raw_payload


def _record_from_transaction(record: PaymentTransactionModel) -> Dict[str, Any]:
    # ORM transaction 轉成前端 / API 共用的 canonical payment record。
    order = record.order
    buyer_username = (
        order.buyer_username_snapshot.strip()
        or (order.buyer.username if order.buyer_id else "")
    )
    trade_params = dict(record.prepared_trade_info_params or {})
    return {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "order_id": order.id,
        "buyer_username": buyer_username,
        "merchant_order_no": record.merchant_order_no,
        "trade_no": record.trade_no or "",
        "status": record.status,
        "status_label": _payment_status_label(record.status, record.source),
        "amount": _format_money(record.amount or "0"),
        "currency": "TWD",
        "payment_url": record.gateway_url or "",
        "return_url": str(trade_params.get("ReturnURL", "")).strip(),
        "client_back_url": str(trade_params.get("ClientBackURL", "")).strip(),
        "created_at": _iso_or_empty(record.created_at),
        "updated_at": _iso_or_empty(record.updated_at),
        "paid_at": _iso_or_empty(record.paid_at),
        "note": _payment_note(record.source),
        "callback_count": int(record.callback_count or 0),
        "raw_payload": _raw_payload_from_transaction(record),
    }


def _sync_local_payment_log(record: Dict[str, Any]) -> Dict[str, Any]:
    # 在 JSON fallback 模式下，以 merchant_order_no 為主鍵覆寫最新狀態；
    # 若還沒有藍新單號，就退回用本地 order_id 對應。
    if _db_payments_enabled():
        return dict(record)
    logs = list(local_store.get_newebpay_payment_logs())
    merchant_order_no = str(record.get("merchant_order_no", "")).strip()
    order_id = int(record.get("order_id") or 0)
    existing = next(
        (
            item
            for item in logs
            if merchant_order_no and str(item.get("merchant_order_no", "")).strip() == merchant_order_no
        ),
        None,
    )
    if existing is None:
        existing = next((item for item in logs if int(item.get("order_id") or 0) == order_id), None)
    canonical = dict(record)
    if existing is None:
        logs.append(canonical)
    else:
        existing.clear()
        existing.update(canonical)
        canonical = existing
    local_store.save_newebpay_payment_logs(logs)
    return dict(canonical)


def _latest_transaction(order_id: int, username: str | None = None) -> PaymentTransactionModel | None:
    if not _db_payments_enabled():
        return None
    queryset = PaymentTransactionModel.objects.select_related("order", "order__buyer").filter(order_id=order_id)
    if username:
        queryset = queryset.filter(order__buyer_username_snapshot=username)
    return queryset.order_by("-updated_at", "-created_at", "-id").first()


def _transaction_for_merchant_order_no(merchant_order_no: str) -> PaymentTransactionModel | None:
    if not _db_payments_enabled():
        return None
    return (
        PaymentTransactionModel.objects.select_related("order", "order__buyer")
        .filter(merchant_order_no=merchant_order_no)
        .order_by("-updated_at", "-id")
        .first()
    )


def _order_for_payment(order_id: int | None) -> OrderModel | None:
    if not order_id or not _db_payments_enabled():
        return None
    return OrderModel.objects.select_related("buyer").filter(id=order_id).first()


class NewebpayConfigurationError(RuntimeError):
    """Raised when required NewebPay settings are missing."""


class NewebpayDependencyError(RuntimeError):
    """Raised when the crypto dependency for sandbox encryption is unavailable."""


@dataclass(slots=True)
class NewebpayRuntimeConfig:
    merchant_id: str
    hash_key: str
    hash_iv: str
    gateway_url: str
    version: str
    respond_type: str
    notify_url: str
    return_url: str
    client_back_url: str
    query_url: str


def _now_timestamp() -> int:
    return int(timezone.now().timestamp())


def _now_iso() -> str:
    return timezone.localtime().isoformat()


def _require_crypto() -> None:
    if not importlib.util.find_spec("Crypto"):
        raise NewebpayDependencyError(
            "NewebPay sandbox 需要 `pycryptodome` 才能進行 TradeInfo 加解密。"
        )


def _load_crypto():
    _require_crypto()
    from Crypto.Cipher import AES  # type: ignore
    from Crypto.Util.Padding import pad, unpad  # type: ignore

    return AES, pad, unpad


def _normalize_return_url(url: str) -> str:
    """Convert callback-style URLs into the browser return endpoint when needed."""
    cleaned = url.strip()
    if cleaned.endswith('/api/v1/integrations/newebpay/payment/sandbox/callback/'):
        return cleaned[:-len('/callback/')] + '/return/'
    return cleaned


def _build_frontend_order_url(order_id: int) -> str:
    """Build the frontend order-detail URL from configured origin."""
    origin = os.getenv('STORE_FRONTEND_ORIGIN', '').strip().rstrip('/')
    if not origin:
        return ''
    return f"{origin}/orders/{order_id}"


def _normalize_client_back_url(url: str, order_id: int) -> str:
    """Normalize ClientBackURL so it always points to the current order page."""
    cleaned = url.strip()
    if not cleaned:
        return _build_frontend_order_url(order_id)
    return re.sub(r'/orders/\d+(?=/?(?:\?|$))', f'/orders/{order_id}', cleaned)


def _normalize_amount(value: Any) -> int:
    decimal_value = Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(decimal_value)


def _format_money(value: Any) -> str:
    return str(Decimal(str(value)).quantize(Decimal('0.01')))


def _env_flag(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return 1
    if raw in {"0", "false", "no", "off"}:
        return 0
    return default


def _enabled_payment_flags() -> Dict[str, int]:
    return {
        flag: _env_flag(PAYMENT_FLAG_ENV_MAP[flag], default)
        for flag, default in DEFAULT_PAYMENT_FLAG_VALUES.items()
        if _env_flag(PAYMENT_FLAG_ENV_MAP[flag], default)
    }


def _load_runtime_config() -> NewebpayRuntimeConfig:
    # 所有 prepare / callback / query 都共用同一份藍新設定，避免不同入口各自拼環境變數。
    merchant_id = os.getenv('NEWEBPAY_MERCHANT_ID', '').strip()
    hash_key = os.getenv('NEWEBPAY_HASH_KEY', '').strip()
    hash_iv = os.getenv('NEWEBPAY_HASH_IV', '').strip()
    gateway_url = os.getenv('NEWEBPAY_PAYMENT_GATEWAY_URL', DEFAULT_GATEWAY_URL).strip() or DEFAULT_GATEWAY_URL
    version = os.getenv('NEWEBPAY_PAYMENT_VERSION', DEFAULT_VERSION).strip() or DEFAULT_VERSION
    respond_type = os.getenv('NEWEBPAY_PAYMENT_RESPOND_TYPE', DEFAULT_RESPOND_TYPE).strip() or DEFAULT_RESPOND_TYPE
    notify_url = os.getenv('NEWEBPAY_PAYMENT_NOTIFY_URL', '').strip()
    return_url = os.getenv('NEWEBPAY_PAYMENT_RETURN_URL', '').strip()
    client_back_url = os.getenv('NEWEBPAY_PAYMENT_CLIENT_BACK_URL', '').strip()
    query_url = os.getenv('NEWEBPAY_PAYMENT_QUERY_URL', DEFAULT_QUERY_URL).strip() or DEFAULT_QUERY_URL

    missing = [
        name
        for name, value in (
            ('NEWEBPAY_MERCHANT_ID', merchant_id),
            ('NEWEBPAY_HASH_KEY', hash_key),
            ('NEWEBPAY_HASH_IV', hash_iv),
        )
        if not value
    ]
    if missing:
        raise NewebpayConfigurationError(f"Missing NewebPay settings: {', '.join(missing)}")

    return NewebpayRuntimeConfig(
        merchant_id=merchant_id,
        hash_key=hash_key,
        hash_iv=hash_iv,
        gateway_url=gateway_url,
        version=version,
        respond_type=respond_type,
        notify_url=notify_url,
        return_url=return_url,
        client_back_url=client_back_url,
        query_url=query_url,
    )


def get_runtime_summary(order_id: int | None = None) -> Dict[str, Any]:
    # 提供後台或 debug API 看憑證、回呼網址、付款方式旗標是否配置完整。
    has_crypto = bool(importlib.util.find_spec('Crypto'))
    summary = {
        'provider': PROVIDER_NAME,
        'mode': MODE_NAME,
        'gateway_url': os.getenv('NEWEBPAY_PAYMENT_GATEWAY_URL', DEFAULT_GATEWAY_URL),
        'has_crypto_dependency': has_crypto,
        'configured': False,
        'missing_settings': [],
    }
    try:
        config = _load_runtime_config()
    except NewebpayConfigurationError as exc:
        missing = str(exc).replace('Missing NewebPay settings: ', '')
        summary['missing_settings'] = [item.strip() for item in missing.split(',') if item.strip()]
        return summary

    summary['configured'] = True
    summary['merchant_id'] = config.merchant_id
    summary['notify_url'] = config.notify_url
    summary['return_url'] = _normalize_return_url(config.return_url)
    summary['client_back_url'] = _normalize_client_back_url(config.client_back_url, order_id) if order_id is not None else config.client_back_url
    summary['query_url'] = config.query_url
    summary['enabled_payment_flags'] = _enabled_payment_flags()
    return summary


def _encrypt_trade_info(plain_text: str, *, hash_key: str, hash_iv: str) -> str:
    AES, pad, _ = _load_crypto()
    cipher = AES.new(hash_key.encode('utf-8'), AES.MODE_CBC, hash_iv.encode('utf-8'))
    encrypted = cipher.encrypt(pad(plain_text.encode('utf-8'), AES.block_size))
    return encrypted.hex()


def _decrypt_trade_info(cipher_hex: str, *, hash_key: str, hash_iv: str) -> str:
    AES, _, unpad = _load_crypto()
    cipher = AES.new(hash_key.encode('utf-8'), AES.MODE_CBC, hash_iv.encode('utf-8'))
    decrypted = cipher.decrypt(bytes.fromhex(cipher_hex))
    return unpad(decrypted, AES.block_size).decode('utf-8')


def _build_trade_sha(cipher_hex: str, *, hash_key: str, hash_iv: str) -> str:
    raw = f'HashKey={hash_key}&{cipher_hex}&HashIV={hash_iv}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest().upper()


def _normalize_decoded_payload(payload: Any) -> Dict[str, Any]:
    # 藍新 Result 有時是 JSON 字串、有時是 querystring，先標準化成 dict 再往下游傳。
    if isinstance(payload, dict):
        result = payload.get('Result')
        if isinstance(result, str):
            result_text = result.strip()
            if result_text:
                try:
                    payload = dict(payload)
                    payload['Result'] = json.loads(result_text)
                except json.JSONDecodeError:
                    parsed_result = dict(parse_qsl(result_text, keep_blank_values=True))
                    if parsed_result:
                        payload = dict(payload)
                        payload['Result'] = parsed_result
        return payload
    return {'raw': payload}


def _decode_trade_info_payload(decrypted: str) -> Dict[str, Any]:
    plain_text = decrypted.strip()
    if not plain_text:
        return {}

    try:
        return _normalize_decoded_payload(json.loads(plain_text))
    except json.JSONDecodeError:
        pass

    parsed_payload = dict(parse_qsl(plain_text, keep_blank_values=True))
    if parsed_payload:
        return _normalize_decoded_payload(parsed_payload)

    return {'raw': decrypted}


def _callback_debug_context(
    *,
    source: str,
    status: str,
    merchant_id: str,
    trade_info: str,
    trade_sha: str,
    decoded_payload: Any | None = None,
) -> Dict[str, Any]:
    context: Dict[str, Any] = {
        'source': source,
        'status': status,
        'merchant_id': merchant_id,
        'trade_info_length': len(trade_info or ''),
        'trade_sha_prefix': (trade_sha or '')[:12],
    }
    if decoded_payload is not None:
        result_fields = extract_callback_result_fields(decoded_payload)
        context.update(
            {
                'merchant_order_no': result_fields.get('merchant_order_no', ''),
                'trade_no': result_fields.get('trade_no', ''),
                'amount': result_fields.get('amount', ''),
                'decoded_keys': sorted(decoded_payload.keys()) if isinstance(decoded_payload, dict) else [],
            }
        )
    return context


def extract_callback_result_fields(decoded_payload: Any) -> Dict[str, str]:
    # callback / query 兩種回傳格式不完全一致，先抽出共同主鍵欄位供後續 lookup。
    merchant_order_no = ''
    trade_no = ''
    amount = ''

    result = decoded_payload.get('Result') if isinstance(decoded_payload, dict) else {}
    if isinstance(result, dict):
        merchant_order_no = str(result.get('MerchantOrderNo', '')).strip()
        trade_no = str(result.get('TradeNo', '')).strip()
        amount = str(result.get('Amt', '')).strip()

    if isinstance(decoded_payload, dict):
        if not merchant_order_no:
            merchant_order_no = str(decoded_payload.get('MerchantOrderNo', '')).strip()
        if not trade_no:
            trade_no = str(decoded_payload.get('TradeNo', '')).strip()
        if not amount:
            amount = str(decoded_payload.get('Amt', '')).strip()

    return {
        'merchant_order_no': merchant_order_no,
        'trade_no': trade_no,
        'amount': amount,
    }


def _result_payload(decoded_payload: Any) -> Dict[str, Any]:
    if isinstance(decoded_payload, dict):
        result = decoded_payload.get('Result')
        if isinstance(result, dict):
            return result
        return decoded_payload
    return {}


def _normalized_payment_method(result: Dict[str, Any]) -> str:
    # 將藍新 PaymentType 映射回站內 payment_method，讓訂單頁與管理端共用既有顯示邏輯。
    payment_type = str(result.get('PaymentType', '')).strip().upper()
    if payment_type.startswith('CREDIT'):
        return order_service.PAYMENT_METHOD_NEWEBPAY_CREDIT
    if payment_type.startswith('GOOGLEPAY') or payment_type.startswith('ANDROIDPAY'):
        return order_service.PAYMENT_METHOD_NEWEBPAY_GOOGLE_PAY
    if payment_type.startswith('SAMSUNGPAY'):
        return order_service.PAYMENT_METHOD_NEWEBPAY_SAMSUNG_PAY
    if payment_type.startswith('WEBATM'):
        return order_service.PAYMENT_METHOD_NEWEBPAY_WEBATM
    if payment_type.startswith('VACC'):
        return order_service.PAYMENT_METHOD_NEWEBPAY_ATM
    if payment_type.startswith('CVSCOM') or any(str(result.get(key, '')).strip() for key in ('StoreCode', 'StoreName', 'StoreAddr')):
        return order_service.PAYMENT_METHOD_NEWEBPAY_CVSCOM
    if payment_type.startswith('CVS'):
        return order_service.PAYMENT_METHOD_NEWEBPAY_CVS
    if payment_type.startswith('BARCODE'):
        return order_service.PAYMENT_METHOD_NEWEBPAY_BARCODE
    return order_service.PAYMENT_METHOD_NEWEBPAY


def _normalized_payment_status(top_level_status: str, result: Dict[str, Any]) -> tuple[str, str]:
    # 先看頂層 Status 是否成功，再依支付型態與 PayTime 判斷是已付款還是待付款。
    if top_level_status.upper() != 'SUCCESS':
        return order_service.PAYMENT_STATUS_FAILED, f"付款失敗 / {top_level_status or 'UNKNOWN'}"

    payment_type = str(result.get('PaymentType', '')).strip().upper()
    pay_time = str(result.get('PayTime', '')).strip()
    immediate_paid_types = ('CREDIT', 'WEBATM', 'GOOGLEPAY', 'SAMSUNGPAY', 'ANDROIDPAY', 'UNIONPAY')

    if pay_time or payment_type.startswith(immediate_paid_types):
        return order_service.PAYMENT_STATUS_PAID, order_service.PAYMENT_STATUS_LABELS[order_service.PAYMENT_STATUS_PAID]
    return order_service.PAYMENT_STATUS_PENDING, order_service.PAYMENT_STATUS_LABELS[order_service.PAYMENT_STATUS_PENDING]


def _extract_store_fields(result: Dict[str, Any]) -> Dict[str, str]:
    # 超商代收 / 取貨付款成功後，訂單還要補齊門市代碼與名稱，這裡集中抽取。
    store_type = str(result.get('StoreType', '')).strip().upper()
    pickup_store_brand = STORE_TYPE_TO_BRAND.get(store_type, '')
    return {
        'pickup_store_brand': pickup_store_brand,
        'pickup_store_code': str(result.get('StoreCode', '')).strip(),
        'pickup_store_name': str(result.get('StoreName', '')).strip(),
        'pickup_store_address': str(result.get('StoreAddr', '')).strip(),
    }


def _query_amount_string(value: Any) -> str:
    return str(_normalize_amount(value))


def _build_query_check_value(*, hash_key: str, hash_iv: str, merchant_id: str, merchant_order_no: str, amount: str) -> str:
    normalized_amount = _query_amount_string(amount)
    payload = urlencode(
        [
            ('Amt', normalized_amount),
            ('MerchantID', merchant_id.strip()),
            ('MerchantOrderNo', merchant_order_no.strip()),
        ]
    )
    raw = f"IV={hash_iv}&{payload}&Key={hash_key}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest().upper()


def _request_query_trade_info(config: NewebpayRuntimeConfig, *, merchant_order_no: str, amount: str) -> Dict[str, Any]:
    # 查單只在 callback 漏掉或訂單狀態仍不明確時使用，避免每次打開訂單都額外打藍新。
    normalized_amount = _query_amount_string(amount)
    payload = {
        'MerchantID': config.merchant_id,
        'Version': DEFAULT_QUERY_VERSION,
        'RespondType': config.respond_type,
        'CheckValue': _build_query_check_value(
            hash_key=config.hash_key,
            hash_iv=config.hash_iv,
            merchant_id=config.merchant_id,
            merchant_order_no=merchant_order_no,
            amount=normalized_amount,
        ),
        'TimeStamp': _now_timestamp(),
        'MerchantOrderNo': merchant_order_no,
        'Amt': normalized_amount,
    }
    encoded = urlencode(payload).encode('utf-8')
    request = Request(config.query_url, data=encoded, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    with urlopen(request, timeout=20) as response:  # nosec B310
        raw = response.read().decode('utf-8')
    return _normalize_decoded_payload(json.loads(raw))


def _latest_payment_record(order_id: int, username: str) -> Dict[str, Any] | None:
    # 同一張訂單可能有多次 prepare / retry，這裡固定回最新一筆支付紀錄。
    transaction = _latest_transaction(order_id, username)
    if transaction is not None:
        return _record_from_transaction(transaction)
    records = [
        item
        for item in local_store.get_newebpay_payment_logs()
        if item.get('mode') == MODE_NAME and item.get('order_id') == order_id and item.get('buyer_username') == username
    ]
    if not records:
        return None
    records.sort(key=lambda item: (item.get('updated_at', ''), item.get('created_at', '')), reverse=True)
    return dict(records[0])


def _latest_payment_record_for_order(order_id: int) -> Dict[str, Any] | None:
    transaction = _latest_transaction(order_id)
    if transaction is not None:
        return _record_from_transaction(transaction)
    records = [
        item
        for item in local_store.get_newebpay_payment_logs()
        if item.get('mode') == MODE_NAME and item.get('order_id') == order_id
    ]
    if not records:
        return None
    records.sort(key=lambda item: (item.get('updated_at', ''), item.get('created_at', '')), reverse=True)
    return dict(records[0])


def _record_query_diagnostic(order_id: int, **values: Any) -> None:
    # 將查單錯誤與原始回應附掛到最新 payment record，方便 debug 不必重現現場。
    transaction = _latest_transaction(order_id)
    if transaction is not None:
        transaction.last_query_error = str(values.get("last_query_error", "") or "")
        transaction.last_query_amount = str(values.get("last_query_amount", "") or "")
        transaction.last_query_merchant_order_no = str(values.get("last_query_merchant_order_no", "") or "")
        response_payload = values.get("last_query_response")
        transaction.last_query_response = response_payload if isinstance(response_payload, dict) else {}
        transaction.last_query_at = timezone.now()
        transaction.save(
            update_fields=[
                "last_query_error",
                "last_query_amount",
                "last_query_merchant_order_no",
                "last_query_response",
                "last_query_at",
                "updated_at",
            ]
        )
        _sync_local_payment_log(_record_from_transaction(transaction))
        return
    if _db_payments_enabled():
        return
    logs = list(local_store.get_newebpay_payment_logs())
    records = [item for item in logs if item.get('mode') == MODE_NAME and item.get('order_id') == order_id]
    if not records:
        return
    records.sort(key=lambda item: (item.get('updated_at', ''), item.get('created_at', '')), reverse=True)
    target = records[0]
    raw_payload = dict(target.get('raw_payload') or {})
    raw_payload.update(values)
    raw_payload['last_query_at'] = _now_iso()
    target['raw_payload'] = raw_payload
    local_store.save_newebpay_payment_logs(logs)


def _should_sync_from_query(order: Dict[str, Any], latest_record: Dict[str, Any] | None) -> bool:
    # 只有付款尚未鎖定、且現有紀錄仍可能落後時，才補打一趟 QueryTradeInfo。
    if not latest_record:
        return False
    merchant_order_no = str(latest_record.get('merchant_order_no', '')).strip()
    amount = str(latest_record.get('amount', '')).strip()
    if not merchant_order_no or not amount:
        return False
    if order.get('status') in {order_service.ORDER_STATUS_CANCELLED, order_service.ORDER_STATUS_REFUNDED}:
        return False
    if order.get('payment_method') == order_service.PAYMENT_METHOD_NEWEBPAY:
        return True
    if not str(order.get('payment_trade_no', '')).strip():
        return True
    if latest_record.get('status') == order_service.PAYMENT_STATUS_PENDING:
        return True
    return False


def sync_order_payment_state(order_id: int) -> Dict[str, Any] | None:
    # 訂單詳情頁打開前，先試著用 query 把藍新狀態補齊，避免 callback 遺漏造成前台停在 pending。
    order = local_store.get_order_by_id(order_id)
    if not order:
        order_model = _order_for_payment(order_id)
        if order_model is not None:
            order = {
                "id": order_model.id,
                "username": order_model.buyer_username_snapshot.strip()
                or (order_model.buyer.username if order_model.buyer_id else ""),
                "status": order_model.status,
                "payment_method": order_model.payment_method,
                "payment_trade_no": order_model.payment_trade_no,
                "items": [],
            }
    if not order:
        return None

    latest_record = _latest_payment_record_for_order(order_id)
    if not _should_sync_from_query(order, latest_record):
        return latest_record

    merchant_order_no = str(latest_record.get('merchant_order_no', '')).strip()
    amount = str(latest_record.get('amount', '')).strip()
    if not merchant_order_no or not amount:
        return latest_record

    # 查單失敗時只記診斷，不中斷使用者查看訂單。
    try:
        config = _load_runtime_config()
        decoded_payload = _request_query_trade_info(
            config,
            merchant_order_no=merchant_order_no,
            amount=amount,
        )
    except Exception as exc:
        _record_query_diagnostic(
            order_id,
            last_query_error=str(exc),
            last_query_amount=_query_amount_string(amount),
            last_query_merchant_order_no=merchant_order_no,
        )
        return latest_record

    result_fields = extract_callback_result_fields(decoded_payload)
    if not result_fields['merchant_order_no']:
        _record_query_diagnostic(
            order_id,
            last_query_error='Query response missing MerchantOrderNo.',
            last_query_amount=_query_amount_string(amount),
            last_query_merchant_order_no=merchant_order_no,
            last_query_response=decoded_payload,
        )
        return latest_record

    _record_query_diagnostic(
        order_id,
        last_query_error='',
        last_query_amount=_query_amount_string(amount),
        last_query_merchant_order_no=merchant_order_no,
        last_query_response=decoded_payload,
    )
    # query 回來後沿用 callback 的 persist 流程，確保 ORM / JSON / 訂單同步只有一套邏輯。
    persist_callback_record(
        {
            'provider': PROVIDER_NAME,
            'mode': MODE_NAME,
            'source': 'query',
            'status': str(decoded_payload.get('Status', '')),
            'merchant_id': config.merchant_id,
            'trade_sha_verified': True,
            'decoded_payload': decoded_payload,
            'received_at': _now_iso(),
        }
    )
    refreshed_order = local_store.get_order_by_id(order_id) or order
    buyer_username = str(refreshed_order.get('username', '')).strip()
    if buyer_username:
        return _latest_payment_record(order_id, buyer_username)
    return _latest_payment_record_for_order(order_id)


def get_payment_record(order_id: int, username: str) -> Dict[str, Any] | None:
    # 使用者訂單頁只會拿到自己的 payment record，並在回傳前先觸發一次狀態同步。
    # checkout 會先組出藍新需要的 form payload，前端再把 form_fields POST 到 gateway_url。
    config = _load_runtime_config()
    order = order_service.get_order_detail_for_user(order_id, username)
    if not order:
        raise ValueError('Order not found.')
    sync_order_payment_state(order_id)
    return _latest_payment_record(order_id, username)


def get_payment_debug(order_id: int) -> Dict[str, Any]:
    # debug 端點需要同時看到 runtime 與所有支付事件，因此這裡直接回完整 records list。
    order = local_store.get_order_by_id(order_id)
    if not order:
        order_model = _order_for_payment(order_id)
        if order_model is None:
            raise ValueError('Order not found.')
        order = {"id": order_model.id}
    sync_order_payment_state(order_id)
    if _db_payments_enabled():
        records = [
            _record_from_transaction(item)
            for item in PaymentTransactionModel.objects.select_related("order", "order__buyer")
            .prefetch_related("callback_logs")
            .filter(order_id=order_id)
            .order_by("-updated_at", "-created_at", "-id")
        ]
    else:
        records = [
            dict(item)
            for item in local_store.get_newebpay_payment_logs()
            if item.get('mode') == MODE_NAME and item.get('order_id') == order_id
        ]
        records.sort(key=lambda item: (item.get('updated_at', ''), item.get('created_at', '')), reverse=True)
    return {
        'runtime': get_runtime_summary(order_id=order_id),
        'records': records,
    }


def _is_payment_locked(order: Dict[str, Any], latest_record: Dict[str, Any] | None) -> bool:
    # 已取消、已退款、已完成履約或已付款的訂單，不應再建立新的藍新付款請求。
    if order.get('status') in {order_service.ORDER_STATUS_CANCELLED, order_service.ORDER_STATUS_REFUNDED}:
        return True
    if all(item.get('seller_status') == order_service.SELLER_STATUS_COMPLETED for item in order.get('items', [])):
        return True
    return bool(latest_record and latest_record.get('status') == order_service.PAYMENT_STATUS_PAID)


def _build_merchant_order_no(order_id: int) -> str:
    """Build a NewebPay-compatible MerchantOrderNo.

    NewebPay MPG accepts only letters, digits, and underscores, with a max
    length of 30 characters.
    """
    return f"{MERCHANT_ORDER_PREFIX}{order_id}_{_now_timestamp()}"


def parse_order_id_from_merchant_order_no(merchant_order_no: str) -> int | None:
    """Extract the local order id from a NewebPay MerchantOrderNo."""
    if not merchant_order_no.startswith(MERCHANT_ORDER_PREFIX):
        return None
    raw = merchant_order_no[len(MERCHANT_ORDER_PREFIX):].split('_', 1)[0]
    return int(raw) if raw.isdigit() else None


def prepare_checkout(
    order_id: int,
    username: str,
    *,
    item_desc_override: str = '',
    email: str = '',
    notify_url: str = '',
    return_url: str = '',
    client_back_url: str = '',
) -> Dict[str, Any]:
    # checkout 建立藍新 form payload 的主入口，前端拿到 form_fields 後直接 POST 到 gateway。
    config = _load_runtime_config()
    order = order_service.get_order_detail_for_user(order_id, username)
    if not order:
        raise ValueError('Order not found.')
    latest_record = _latest_payment_record(order_id, username)
    if _is_payment_locked(order, latest_record):
        raise ValueError('This order can no longer create a new payment request.')

    item_names = [item.get('name', '') for item in order.get('items', []) if item.get('name')]
    item_desc = item_desc_override.strip() or ', '.join(item_names) or f'Order {order_id}'
    merchant_order_no = _build_merchant_order_no(order_id)
    amount = _normalize_amount(order.get('totals', {}).get('total', order.get('total_amount', '0')))

    resolved_notify_url = notify_url.strip() or config.notify_url
    resolved_return_url = _normalize_return_url(return_url.strip() or config.return_url)
    resolved_client_back_url = _normalize_client_back_url(client_back_url.strip() or config.client_back_url, order_id)

    # 先整理藍新 MPG 明文欄位，再加密成 TradeInfo / TradeSha。
    trade_info_params: Dict[str, Any] = {
        'MerchantID': config.merchant_id,
        'RespondType': config.respond_type,
        'TimeStamp': _now_timestamp(),
        'Version': config.version,
        'MerchantOrderNo': merchant_order_no,
        'Amt': amount,
        'ItemDesc': item_desc,
        'NotifyURL': resolved_notify_url,
        'ReturnURL': resolved_return_url,
        'ClientBackURL': resolved_client_back_url,
        'Email': email.strip(),
        'LoginType': 0,
    }
    trade_info_params.update(_enabled_payment_flags())
    trade_info_params['CVSCOM'] = 1 if order.get('shipping_method') == order_service.SHIPPING_METHOD_CONVENIENCE_STORE else 0
    trade_info_params = {key: value for key, value in trade_info_params.items() if value not in ('', None)}

    plain_text = urlencode(trade_info_params)
    trade_info = _encrypt_trade_info(plain_text, hash_key=config.hash_key, hash_iv=config.hash_iv)
    trade_sha = _build_trade_sha(trade_info, hash_key=config.hash_key, hash_iv=config.hash_iv)

    return {
        'provider': PROVIDER_NAME,
        'mode': MODE_NAME,
        'order_id': order_id,
        'buyer_username': username,
        'gateway_url': config.gateway_url,
        'form_method': 'POST',
        'merchant_order_no': merchant_order_no,
        'trade_info_params': trade_info_params,
        'form_fields': {
            'MerchantID': config.merchant_id,
            'TradeInfo': trade_info,
            'TradeSha': trade_sha,
            'Version': config.version,
            'EncryptType': 0,
        },
        'note': '請將 form_fields 以 HTML form POST 到 gateway_url，送往藍新 sandbox。', 
    }


def persist_prepared_attempt(prepared: Dict[str, Any]) -> Dict[str, Any]:
    # prepare 完成後先落盤，讓 callback / query 能依 merchant_order_no 找回這次付款嘗試。
    now = _now_iso()
    order_id = int(prepared['order_id'])
    buyer_username = str(prepared['buyer_username'])
    merchant_order_no = str(prepared['merchant_order_no'])
    trade_params = dict(prepared.get('trade_info_params') or {})

    record = {
        'provider': PROVIDER_NAME,
        'mode': MODE_NAME,
        'order_id': order_id,
        'buyer_username': buyer_username,
        'merchant_order_no': merchant_order_no,
        'trade_no': '',
        'status': order_service.PAYMENT_STATUS_PENDING,
        'status_label': '已建立 sandbox payload',
        'amount': _format_money(trade_params.get('Amt', '0')),
        'currency': 'TWD',
        'payment_url': prepared.get('gateway_url', ''),
        'return_url': trade_params.get('ReturnURL', ''),
        'client_back_url': trade_params.get('ClientBackURL', ''),
        'created_at': now,
        'updated_at': now,
        'paid_at': '',
        'note': 'sandbox prepare',
        'callback_count': 0,
        'raw_payload': {
            'prepared_form_fields': prepared.get('form_fields', {}),
            'prepared_trade_info_params': trade_params,
            'events': [],
        },
    }

    # ORM 模式下用 PaymentTransaction 承接，JSON fallback 則沿用 canonical record 保存。
    if _db_payments_enabled():
        order_model = _order_for_payment(order_id)
        if order_model is not None:
            transaction, _ = PaymentTransactionModel.objects.update_or_create(
                order=order_model,
                merchant_order_no=merchant_order_no,
                defaults={
                    'provider': PROVIDER_NAME,
                    'source': PaymentSourceModel.PREPARE,
                    'status': PaymentStatusModel.PENDING,
                    'amount': Decimal(str(_normalize_amount(trade_params.get('Amt', '0')))),
                    'merchant_id': str((prepared.get('form_fields') or {}).get('MerchantID', '')).strip(),
                    'trade_no': '',
                    'payment_type_code': '',
                    'payment_method_label': order_service.PAYMENT_METHOD_LABELS.get(
                        order_model.payment_method,
                        order_model.payment_method,
                    ),
                    'gateway_url': prepared.get('gateway_url', ''),
                    'callback_count': 0,
                    'prepared_form_fields': prepared.get('form_fields', {}),
                    'prepared_trade_info_params': trade_params,
                    'latest_raw_payload': {},
                    'latest_result_payload': {},
                    'paid_at': None,
                },
            )
            record = _record_from_transaction(transaction)

    return _sync_local_payment_log(record)


def handle_callback(
    *,
    status: str,
    merchant_id: str,
    trade_info: str,
    trade_sha: str,
    source: str = 'callback',
) -> Dict[str, Any]:
    # callback 只負責驗章與解密，不在這一層直接改訂單，方便 return / query 共用同一份解析結果。
    config = _load_runtime_config()
    expected_sha = _build_trade_sha(trade_info, hash_key=config.hash_key, hash_iv=config.hash_iv)
    if expected_sha != trade_sha:
        logger.warning(
            "NewebPay callback TradeSha mismatch.",
            extra=_callback_debug_context(
                source=source,
                status=status,
                merchant_id=merchant_id,
                trade_info=trade_info,
                trade_sha=trade_sha,
            ),
        )
        raise ValueError('Invalid TradeSha.')
    if merchant_id != config.merchant_id:
        logger.warning(
            "NewebPay callback merchant_id mismatch.",
            extra=_callback_debug_context(
                source=source,
                status=status,
                merchant_id=merchant_id,
                trade_info=trade_info,
                trade_sha=trade_sha,
            ),
        )
        raise ValueError('MerchantID does not match configured sandbox merchant.')

    try:
        decrypted = _decrypt_trade_info(trade_info, hash_key=config.hash_key, hash_iv=config.hash_iv)
    except Exception:
        logger.exception(
            "NewebPay callback TradeInfo decrypt failed.",
            extra=_callback_debug_context(
                source=source,
                status=status,
                merchant_id=merchant_id,
                trade_info=trade_info,
                trade_sha=trade_sha,
            ),
        )
        raise
    decoded_payload = _decode_trade_info_payload(decrypted)
    result_fields = extract_callback_result_fields(decoded_payload)
    if not result_fields['merchant_order_no']:
        logger.warning(
            "NewebPay callback decoded successfully but merchant_order_no is missing.",
            extra=_callback_debug_context(
                source=source,
                status=status,
                merchant_id=merchant_id,
                trade_info=trade_info,
                trade_sha=trade_sha,
                decoded_payload=decoded_payload,
            ),
        )
    else:
        logger.info(
            "NewebPay callback decoded successfully.",
            extra=_callback_debug_context(
                source=source,
                status=status,
                merchant_id=merchant_id,
                trade_info=trade_info,
                trade_sha=trade_sha,
                decoded_payload=decoded_payload,
            ),
        )

    return {
        'provider': PROVIDER_NAME,
        'mode': MODE_NAME,
        'source': source,
        'status': status,
        'merchant_id': merchant_id,
        'trade_sha_verified': True,
        'decoded_payload': decoded_payload,
        'trade_info_base64': base64.b64encode(trade_info.encode('utf-8')).decode('ascii'),
        'received_at': _now_iso(),
    }


def persist_callback_record(record: Dict[str, Any]) -> Dict[str, Any]:
    # 真正把 callback / return / query 結果寫回 payment record，並同步訂單付款狀態。
    decoded = record.get('decoded_payload') or {}
    result = _result_payload(decoded)
    result_fields = extract_callback_result_fields(decoded)
    merchant_order_no = result_fields['merchant_order_no']
    trade_no = result_fields['trade_no']
    amount = result_fields['amount']

    order_id = parse_order_id_from_merchant_order_no(merchant_order_no)
    buyer_username = ''
    # 先從本地訂單或 ORM 訂單找 buyer，讓紀錄可以回掛到正確帳號。
    if order_id is not None:
        order = local_store.get_order_by_id(order_id)
        if order:
            buyer_username = str(order.get('username', '')).strip()
    if not buyer_username and order_id is not None:
        order_model = _order_for_payment(order_id)
        if order_model is not None:
            buyer_username = order_model.buyer_username_snapshot.strip() or (order_model.buyer.username if order_model.buyer_id else '')

    status_value = str(record.get('status', '')).strip()
    normalized_status, status_label = _normalized_payment_status(status_value, result)
    payment_method = _normalized_payment_method(result)
    store_fields = _extract_store_fields(result)
    now = _now_iso()
    source = str(record.get('source', PaymentSourceModel.CALLBACK)).strip() or PaymentSourceModel.CALLBACK
    prepared_record = None
    if order_id is not None and buyer_username:
        prepared_record = _latest_payment_record(order_id, buyer_username)
    if prepared_record is None and order_id is not None:
        prepared_record = _latest_payment_record_for_order(order_id)

    persisted_record = {
        'provider': PROVIDER_NAME,
        'mode': MODE_NAME,
        'order_id': order_id or 0,
        'buyer_username': buyer_username,
        'merchant_order_no': merchant_order_no,
        'trade_no': trade_no,
        'status': normalized_status,
        'status_label': status_label,
        'amount': _format_money(amount or '0'),
        'currency': 'TWD',
        'payment_url': str((prepared_record or {}).get('payment_url', '')).strip(),
        'return_url': str((prepared_record or {}).get('return_url', '')).strip(),
        'client_back_url': str((prepared_record or {}).get('client_back_url', '')).strip(),
        'created_at': str((prepared_record or {}).get('created_at', now)).strip() or now,
        'updated_at': now,
        'paid_at': now if normalized_status == order_service.PAYMENT_STATUS_PAID else '',
        'note': _payment_note(source),
        'callback_count': int((prepared_record or {}).get('callback_count', 0) or 0) + 1,
        'raw_payload': {
            **dict((prepared_record or {}).get('raw_payload') or {}),
            'latest_record': dict(record),
        },
    }

    # ORM 存在時，prepare / callback / query 全都收斂到同一筆 transaction 與 callback log。
    if _db_payments_enabled():
        order_model = _order_for_payment(order_id) if order_id is not None else None
        if order_model is not None:
            transaction = _transaction_for_merchant_order_no(merchant_order_no)
            if transaction is None:
                transaction = PaymentTransactionModel.objects.create(
                    order=order_model,
                    provider=PROVIDER_NAME,
                    source=source,
                    status=normalized_status,
                    amount=Decimal(str(_normalize_amount(amount or '0'))),
                    merchant_id=str(record.get('merchant_id', '')).strip(),
                    merchant_order_no=merchant_order_no,
                    trade_no=trade_no,
                    payment_type_code=str(result.get('PaymentType', '')).strip(),
                    payment_method_label=order_service.PAYMENT_METHOD_LABELS.get(payment_method, payment_method),
                    gateway_url=str((prepared_record or {}).get('payment_url', '')).strip(),
                    callback_count=0,
                    prepared_form_fields=dict((prepared_record or {}).get('raw_payload', {}).get('prepared_form_fields') or {}),
                    prepared_trade_info_params=dict((prepared_record or {}).get('raw_payload', {}).get('prepared_trade_info_params') or {}),
                    latest_raw_payload={},
                    latest_result_payload={},
                )
            transaction.source = source
            transaction.status = normalized_status
            transaction.amount = Decimal(str(_normalize_amount(amount or '0')))
            transaction.merchant_id = str(record.get('merchant_id', '')).strip()
            transaction.trade_no = trade_no or transaction.trade_no
            transaction.payment_type_code = str(result.get('PaymentType', '')).strip()
            transaction.payment_method_label = order_service.PAYMENT_METHOD_LABELS.get(payment_method, payment_method)
            transaction.callback_count = int(transaction.callback_count or 0) + 1
            transaction.latest_raw_payload = {'latest_record': dict(record)}
            transaction.latest_result_payload = dict(result)
            if normalized_status == order_service.PAYMENT_STATUS_PAID:
                pay_time = _aware_datetime_or_none(str(result.get('PayTime', '')).strip())
                transaction.paid_at = pay_time or timezone.now()
            transaction.save()
            PaymentCallbackLogModel.objects.create(
                payment_transaction=transaction,
                order=order_model,
                provider=PROVIDER_NAME,
                source=source,
                is_success=normalized_status != order_service.PAYMENT_STATUS_FAILED,
                http_status=200,
                raw_payload=dict(record),
                parsed_payload=dict(decoded) if isinstance(decoded, dict) else {},
                note=_payment_note(source),
            )
            persisted_record = _record_from_transaction(transaction)

    persisted_record = _sync_local_payment_log(persisted_record)
    # 最後透過既有 order service 寫回訂單主狀態與超商門市資訊，避免這支 service 直接散改訂單欄位。
    if order_id is not None:
        order_service.apply_newebpay_result(
            order_id,
            payment_method=payment_method,
            payment_status=normalized_status,
            trade_no=trade_no,
            paid_at=str(persisted_record.get('paid_at', '')).strip(),
            pickup_store_brand=store_fields['pickup_store_brand'],
            pickup_store_code=store_fields['pickup_store_code'],
            pickup_store_name=store_fields['pickup_store_name'],
            pickup_store_address=store_fields['pickup_store_address'],
        )
    return dict(persisted_record)
