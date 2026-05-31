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
from urllib.parse import urlencode

from django.utils import timezone

from ..repositories import local_store
from . import orders as order_service

PROVIDER_NAME = "NewebPay Payment"
MODE_NAME = "sandbox"
DEFAULT_GATEWAY_URL = "https://ccore.newebpay.com/MPG/mpg_gateway"
DEFAULT_VERSION = "2.2"
DEFAULT_RESPOND_TYPE = "JSON"


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

    item_names = [item.get('name', '') for item in order.get('items', []) if item.get('name')]
    item_desc = item_desc_override.strip() or ', '.join(item_names) or f'Order {order_id}'
    merchant_order_no = f'ORDER{order_id}-{_now_timestamp()}'
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
            },
        }
        records.append(record)
    else:
        record['updated_at'] = now
        record['payment_url'] = prepared.get('gateway_url', '')
        record['return_url'] = trade_params.get('ReturnURL', '')
        record['client_back_url'] = trade_params.get('ClientBackURL', '')
        record['raw_payload'] = {
            'prepared_form_fields': prepared.get('form_fields', {}),
            'prepared_trade_info_params': trade_params,
        }

    local_store.save_newebpay_payment_logs(records)
    return dict(record)


def handle_callback(
    *,
    status: str,
    merchant_id: str,
    trade_info: str,
    trade_sha: str,
) -> Dict[str, Any]:
    config = _load_runtime_config()
    expected_sha = _build_trade_sha(trade_info, hash_key=config.hash_key, hash_iv=config.hash_iv)
    if expected_sha != trade_sha:
        raise ValueError('Invalid TradeSha.')
    if merchant_id != config.merchant_id:
        raise ValueError('MerchantID does not match configured sandbox merchant.')

    decrypted = _decrypt_trade_info(trade_info, hash_key=config.hash_key, hash_iv=config.hash_iv)
    try:
        decoded_payload = json.loads(decrypted)
    except json.JSONDecodeError:
        decoded_payload = {'raw': decrypted}

    return {
        'provider': PROVIDER_NAME,
        'mode': MODE_NAME,
        'status': status,
        'merchant_id': merchant_id,
        'trade_sha_verified': True,
        'decoded_payload': decoded_payload,
        'trade_info_base64': base64.b64encode(trade_info.encode('utf-8')).decode('ascii'),
    }


def persist_callback_record(record: Dict[str, Any]) -> Dict[str, Any]:
    decoded = record.get('decoded_payload') or {}
    result = decoded.get('Result') if isinstance(decoded, dict) else {}
    merchant_order_no = ''
    trade_no = ''
    amount = ''
    if isinstance(result, dict):
        merchant_order_no = str(result.get('MerchantOrderNo', '')).strip()
        trade_no = str(result.get('TradeNo', '')).strip()
        amount = str(result.get('Amt', '')).strip()
    if not merchant_order_no and isinstance(decoded, dict):
        merchant_order_no = str(decoded.get('MerchantOrderNo', '')).strip()
    if not trade_no and isinstance(decoded, dict):
        trade_no = str(decoded.get('TradeNo', '')).strip()
    if not amount and isinstance(decoded, dict):
        amount = str(decoded.get('Amt', '')).strip()

    raw_id = merchant_order_no[5:].split('-', 1)[0] if merchant_order_no.startswith('ORDER') else ''
    order_id = int(raw_id) if raw_id.isdigit() else None
    buyer_username = ''
    if order_id is not None:
        order = local_store.get_order_by_id(order_id)
        if order:
            buyer_username = str(order.get('username', '')).strip()

    status_value = str(record.get('status', '')).strip()
    normalized_status = 'paid' if status_value.upper() == 'SUCCESS' else 'failed'
    status_label = '付款成功' if normalized_status == 'paid' else f'付款失敗 / {status_value or "UNKNOWN"}'

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
            'paid_at': now if normalized_status == 'paid' else '',
            'note': 'sandbox callback',
            'callback_count': 1,
            'raw_payload': record,
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
        if normalized_status == 'paid':
            existing['paid_at'] = now
        existing['raw_payload'] = record

    local_store.save_newebpay_payment_logs(logs)
    return dict(existing)
