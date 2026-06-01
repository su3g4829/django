"""NewebPay sandbox payment service.

Responsibilities:
- load MerchantID / HashKey / HashIV runtime settings
- build MPG form-post payload for sandbox checkout
- verify callback TradeSha and decode TradeInfo
- persist prepare / callback records into local JSON storage
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
from urllib.parse import parse_qsl, urlencode

from django.utils import timezone

from ..repositories import local_store
from . import orders as order_service

PROVIDER_NAME = "NewebPay Payment"
MODE_NAME = "sandbox"
DEFAULT_GATEWAY_URL = "https://ccore.newebpay.com/MPG/mpg_gateway"
DEFAULT_VERSION = "2.2"
DEFAULT_RESPOND_TYPE = "JSON"
MERCHANT_ORDER_PREFIX = "ORDER"
ENABLED_PAYMENT_FLAGS = {
    "WEBATM": 1,
    "VACC": 1,
    "CVS": 1,
    "BARCODE": 1,
    "ANDROIDPAY": 1,
    "SAMSUNGPAY": 1,
}
STORE_TYPE_TO_BRAND = {
    "7-ELEVEN": "UNIMART",
    "UNIMART": "UNIMART",
    "FAMILY": "FAMI",
    "FAMI": "FAMI",
    "全家": "FAMI",
}


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


def _load_runtime_config() -> NewebpayRuntimeConfig:
    merchant_id = os.getenv('NEWEBPAY_MERCHANT_ID', '').strip()
    hash_key = os.getenv('NEWEBPAY_HASH_KEY', '').strip()
    hash_iv = os.getenv('NEWEBPAY_HASH_IV', '').strip()
    gateway_url = os.getenv('NEWEBPAY_PAYMENT_GATEWAY_URL', DEFAULT_GATEWAY_URL).strip() or DEFAULT_GATEWAY_URL
    version = os.getenv('NEWEBPAY_PAYMENT_VERSION', DEFAULT_VERSION).strip() or DEFAULT_VERSION
    respond_type = os.getenv('NEWEBPAY_PAYMENT_RESPOND_TYPE', DEFAULT_RESPOND_TYPE).strip() or DEFAULT_RESPOND_TYPE
    notify_url = os.getenv('NEWEBPAY_PAYMENT_NOTIFY_URL', '').strip()
    return_url = os.getenv('NEWEBPAY_PAYMENT_RETURN_URL', '').strip()
    client_back_url = os.getenv('NEWEBPAY_PAYMENT_CLIENT_BACK_URL', '').strip()

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
    )


def get_runtime_summary(order_id: int | None = None) -> Dict[str, Any]:
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


def extract_callback_result_fields(decoded_payload: Any) -> Dict[str, str]:
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
    if top_level_status.upper() != 'SUCCESS':
        return order_service.PAYMENT_STATUS_FAILED, f"付款失敗 / {top_level_status or 'UNKNOWN'}"

    payment_type = str(result.get('PaymentType', '')).strip().upper()
    pay_time = str(result.get('PayTime', '')).strip()
    immediate_paid_types = ('CREDIT', 'WEBATM', 'GOOGLEPAY', 'SAMSUNGPAY', 'ANDROIDPAY', 'UNIONPAY')

    if pay_time or payment_type.startswith(immediate_paid_types):
        return order_service.PAYMENT_STATUS_PAID, order_service.PAYMENT_STATUS_LABELS[order_service.PAYMENT_STATUS_PAID]
    return order_service.PAYMENT_STATUS_PENDING, order_service.PAYMENT_STATUS_LABELS[order_service.PAYMENT_STATUS_PENDING]


def _extract_store_fields(result: Dict[str, Any]) -> Dict[str, str]:
    store_type = str(result.get('StoreType', '')).strip().upper()
    pickup_store_brand = STORE_TYPE_TO_BRAND.get(store_type, '')
    return {
        'pickup_store_brand': pickup_store_brand,
        'pickup_store_code': str(result.get('StoreCode', '')).strip(),
        'pickup_store_name': str(result.get('StoreName', '')).strip(),
        'pickup_store_address': str(result.get('StoreAddr', '')).strip(),
    }


def _latest_payment_record(order_id: int, username: str) -> Dict[str, Any] | None:
    records = [
        item
        for item in local_store.get_newebpay_payment_logs()
        if item.get('mode') == MODE_NAME and item.get('order_id') == order_id and item.get('buyer_username') == username
    ]
    if not records:
        return None
    records.sort(key=lambda item: (item.get('updated_at', ''), item.get('created_at', '')), reverse=True)
    return dict(records[0])


def get_payment_record(order_id: int, username: str) -> Dict[str, Any] | None:
    order = order_service.get_order_detail_for_user(order_id, username)
    if not order:
        raise ValueError('Order not found.')
    return _latest_payment_record(order_id, username)


def get_payment_debug(order_id: int) -> Dict[str, Any]:
    order = local_store.get_order_by_id(order_id)
    if not order:
        raise ValueError('Order not found.')
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
    trade_info_params.update(ENABLED_PAYMENT_FLAGS)
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
    records = list(local_store.get_newebpay_payment_logs())
    now = _now_iso()
    order_id = int(prepared['order_id'])
    buyer_username = str(prepared['buyer_username'])
    merchant_order_no = str(prepared['merchant_order_no'])
    trade_params = dict(prepared.get('trade_info_params') or {})

    record = next((item for item in records if item.get('merchant_order_no') == merchant_order_no), None)
    if record is None:
        record = {
            'provider': PROVIDER_NAME,
            'mode': MODE_NAME,
            'order_id': order_id,
            'buyer_username': buyer_username,
            'merchant_order_no': merchant_order_no,
            'trade_no': '',
            'status': 'pending',
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
        records.append(record)
    else:
        record['updated_at'] = now
        record['payment_url'] = prepared.get('gateway_url', '')
        record['return_url'] = trade_params.get('ReturnURL', '')
        record['client_back_url'] = trade_params.get('ClientBackURL', '')
        existing_raw_payload = dict(record.get('raw_payload') or {})
        existing_raw_payload['prepared_form_fields'] = prepared.get('form_fields', {})
        existing_raw_payload['prepared_trade_info_params'] = trade_params
        existing_raw_payload.setdefault('events', [])
        record['raw_payload'] = existing_raw_payload

    local_store.save_newebpay_payment_logs(records)
    return dict(record)


def handle_callback(
    *,
    status: str,
    merchant_id: str,
    trade_info: str,
    trade_sha: str,
    source: str = 'callback',
) -> Dict[str, Any]:
    config = _load_runtime_config()
    expected_sha = _build_trade_sha(trade_info, hash_key=config.hash_key, hash_iv=config.hash_iv)
    if expected_sha != trade_sha:
        raise ValueError('Invalid TradeSha.')
    if merchant_id != config.merchant_id:
        raise ValueError('MerchantID does not match configured sandbox merchant.')

    decrypted = _decrypt_trade_info(trade_info, hash_key=config.hash_key, hash_iv=config.hash_iv)
    decoded_payload = _decode_trade_info_payload(decrypted)

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
    decoded = record.get('decoded_payload') or {}
    result = _result_payload(decoded)
    result_fields = extract_callback_result_fields(decoded)
    merchant_order_no = result_fields['merchant_order_no']
    trade_no = result_fields['trade_no']
    amount = result_fields['amount']

    order_id = parse_order_id_from_merchant_order_no(merchant_order_no)
    buyer_username = ''
    if order_id is not None:
        order = local_store.get_order_by_id(order_id)
        if order:
            buyer_username = str(order.get('username', '')).strip()

    status_value = str(record.get('status', '')).strip()
    normalized_status, status_label = _normalized_payment_status(status_value, result)
    payment_method = _normalized_payment_method(result)
    store_fields = _extract_store_fields(result)
    status_label = _normalized_payment_status(status_value, result)[1]
    status_label = '付款成功' if normalized_status == 'paid' else f'付款失敗 / {status_value or "UNKNOWN"}'

    status_label = _normalized_payment_status(status_value, result)[1]
    logs = list(local_store.get_newebpay_payment_logs())
    existing = next((item for item in logs if merchant_order_no and item.get('merchant_order_no') == merchant_order_no), None)
    now = _now_iso()
    if existing is None:
        existing = {
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
            'payment_url': '',
            'return_url': '',
            'client_back_url': '',
            'created_at': now,
            'updated_at': now,
            'paid_at': now if normalized_status == order_service.PAYMENT_STATUS_PAID else '',
            'note': 'sandbox callback',
            'callback_count': 1,
            'raw_payload': {
                'events': [dict(record)],
            },
        }
        logs.append(existing)
    else:
        existing['trade_no'] = trade_no or existing.get('trade_no', '')
        existing['status'] = normalized_status
        existing['status_label'] = status_label
        if amount:
            existing['amount'] = _format_money(amount)
        existing['updated_at'] = now
        existing['callback_count'] = int(existing.get('callback_count', 0)) + 1
        if normalized_status == order_service.PAYMENT_STATUS_PAID:
            existing['paid_at'] = now
        raw_payload = dict(existing.get('raw_payload') or {})
        events = list(raw_payload.get('events') or [])
        events.append(dict(record))
        raw_payload['events'] = events
        existing['raw_payload'] = raw_payload

    local_store.save_newebpay_payment_logs(logs)
    if order_id is not None:
        order_service.apply_newebpay_result(
            order_id,
            payment_method=payment_method,
            payment_status=normalized_status,
            trade_no=trade_no,
            paid_at=existing.get('paid_at', ''),
            pickup_store_brand=store_fields['pickup_store_brand'],
            pickup_store_code=store_fields['pickup_store_code'],
            pickup_store_name=store_fields['pickup_store_name'],
            pickup_store_address=store_fields['pickup_store_address'],
        )
    return dict(existing)
