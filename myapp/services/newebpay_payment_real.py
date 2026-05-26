"""藍新支付 sandbox 測試版 service。

這個模組的定位是「正式串接前的最小可測架構」：
- 讀取 MerchantID / HashKey / HashIV 等環境變數
- 依官方 MPG 幕前支付規格組出 form post payload
- 提供 callback 驗簽與 TradeInfo 解密

注意：
- 這不是完整正式版金流流程，目的是先讓 Render / ngrok 可測 sandbox。
- 由於本機目前未安裝 AES 套件，真正執行加解密時需要 `pycryptodome`。
- 物流與不同支付工具的細節仍可能要依商店後台最新版藍新文件微調。
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
from urllib.parse import urlencode

from django.utils import timezone

from . import orders as order_service

PROVIDER_NAME = "NewebPay Payment"
MODE_NAME = "sandbox"
DEFAULT_GATEWAY_URL = "https://ccore.newebpay.com/MPG/mpg_gateway"
DEFAULT_VERSION = "2.2"
DEFAULT_RESPOND_TYPE = "JSON"


class NewebpayConfigurationError(RuntimeError):
    """藍新環境變數未設定完整。"""


class NewebpayDependencyError(RuntimeError):
    """缺少藍新 sandbox 所需的加解密依賴。"""


@dataclass(slots=True)
class NewebpayRuntimeConfig:
    """保存藍新正式 sandbox 所需設定。"""

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
    """產生藍新 TradeInfo 常用的 Unix timestamp。"""
    return int(timezone.now().timestamp())


def _require_crypto() -> None:
    """確認本機已安裝 `pycryptodome`。

    Render 正式部署時只要 `requirements.txt` 有安裝即可。
    本機若未安裝，會在真正呼叫 sandbox prepare / callback decode 時拋出清楚錯誤。
    """
    if not importlib.util.find_spec("Crypto"):
        raise NewebpayDependencyError(
            "NewebPay sandbox 需要 pycryptodome。請先安裝 `pycryptodome` 後再測試正式 sandbox。"
        )


def _load_crypto():
    """延遲匯入 Crypto，避免在 Django 啟動階段就因未安裝而失敗。"""
    _require_crypto()
    from Crypto.Cipher import AES  # type: ignore
    from Crypto.Util.Padding import pad, unpad  # type: ignore

    return AES, pad, unpad


def _normalize_amount(value: Any) -> int:
    """將目前專案的 Decimal 總額轉成藍新 MPG 需要的整數金額。

    藍新 MPG 的 `Amt` 是整數欄位；此專案現有測試資料含小數，因此先採四捨五入。
    若未來正式上線，建議在價格模型層直接採整數金額或明確規範 rounding 策略。
    """
    decimal_value = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(decimal_value)


def _load_runtime_config() -> NewebpayRuntimeConfig:
    """從環境變數讀取藍新正式 sandbox 設定。"""
    merchant_id = os.getenv("NEWEBPAY_MERCHANT_ID", "").strip()
    hash_key = os.getenv("NEWEBPAY_HASH_KEY", "").strip()
    hash_iv = os.getenv("NEWEBPAY_HASH_IV", "").strip()
    gateway_url = os.getenv("NEWEBPAY_PAYMENT_GATEWAY_URL", DEFAULT_GATEWAY_URL).strip() or DEFAULT_GATEWAY_URL
    version = os.getenv("NEWEBPAY_PAYMENT_VERSION", DEFAULT_VERSION).strip() or DEFAULT_VERSION
    respond_type = os.getenv("NEWEBPAY_PAYMENT_RESPOND_TYPE", DEFAULT_RESPOND_TYPE).strip() or DEFAULT_RESPOND_TYPE
    notify_url = os.getenv("NEWEBPAY_PAYMENT_NOTIFY_URL", "").strip()
    return_url = os.getenv("NEWEBPAY_PAYMENT_RETURN_URL", "").strip()
    client_back_url = os.getenv("NEWEBPAY_PAYMENT_CLIENT_BACK_URL", "").strip()

    missing = [
        name
        for name, value in (
            ("NEWEBPAY_MERCHANT_ID", merchant_id),
            ("NEWEBPAY_HASH_KEY", hash_key),
            ("NEWEBPAY_HASH_IV", hash_iv),
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


def get_runtime_summary() -> Dict[str, Any]:
    """回傳目前正式 sandbox 可用性摘要，供 API / 文件頁檢查。"""
    has_crypto = bool(importlib.util.find_spec("Crypto"))
    summary = {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "gateway_url": os.getenv("NEWEBPAY_PAYMENT_GATEWAY_URL", DEFAULT_GATEWAY_URL),
        "has_crypto_dependency": has_crypto,
        "configured": False,
        "missing_settings": [],
    }
    try:
        config = _load_runtime_config()
    except NewebpayConfigurationError as exc:
        missing = str(exc).replace("Missing NewebPay settings: ", "")
        summary["missing_settings"] = [item.strip() for item in missing.split(",") if item.strip()]
        return summary

    summary["configured"] = True
    summary["merchant_id"] = config.merchant_id
    summary["notify_url"] = config.notify_url
    summary["return_url"] = config.return_url
    summary["client_back_url"] = config.client_back_url
    return summary


def _encrypt_trade_info(plain_text: str, *, hash_key: str, hash_iv: str) -> str:
    """用藍新舊制 AES/CBC/PKCS7 模式加密 TradeInfo。"""
    AES, pad, _ = _load_crypto()
    cipher = AES.new(hash_key.encode("utf-8"), AES.MODE_CBC, hash_iv.encode("utf-8"))
    encrypted = cipher.encrypt(pad(plain_text.encode("utf-8"), AES.block_size))
    return encrypted.hex()


def _decrypt_trade_info(cipher_hex: str, *, hash_key: str, hash_iv: str) -> str:
    """解密藍新 callback 帶回的 TradeInfo。"""
    AES, _, unpad = _load_crypto()
    cipher = AES.new(hash_key.encode("utf-8"), AES.MODE_CBC, hash_iv.encode("utf-8"))
    decrypted = cipher.decrypt(bytes.fromhex(cipher_hex))
    return unpad(decrypted, AES.block_size).decode("utf-8")


def _build_trade_sha(cipher_hex: str, *, hash_key: str, hash_iv: str) -> str:
    """依藍新 MPG 規格生成 TradeSha。"""
    raw = f"HashKey={hash_key}&{cipher_hex}&HashIV={hash_iv}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def prepare_checkout(
    order_id: int,
    username: str,
    *,
    item_desc_override: str = "",
    email: str = "",
    notify_url: str = "",
    return_url: str = "",
    client_back_url: str = "",
) -> Dict[str, Any]:
    """建立藍新 sandbox 的 form post payload。

    回傳結果可直接提供給前端生成 HTML form，再 POST 到藍新 sandbox gateway。
    """
    config = _load_runtime_config()
    order = order_service.get_order_detail_for_user(order_id, username)
    if not order:
        raise ValueError("Order not found.")

    item_names = [item.get("name", "") for item in order.get("items", []) if item.get("name")]
    item_desc = item_desc_override.strip() or ", ".join(item_names) or f"Order {order_id}"
    merchant_order_no = f"ORDER{order_id}-{_now_timestamp()}"
    amount = _normalize_amount(order.get("totals", {}).get("total", order.get("total_amount", "0")))

    trade_info_params: Dict[str, Any] = {
        "MerchantID": config.merchant_id,
        "RespondType": config.respond_type,
        "TimeStamp": _now_timestamp(),
        "Version": config.version,
        "MerchantOrderNo": merchant_order_no,
        "Amt": amount,
        "ItemDesc": item_desc,
        "NotifyURL": notify_url.strip() or config.notify_url,
        "ReturnURL": return_url.strip() or config.return_url,
        "ClientBackURL": client_back_url.strip() or config.client_back_url,
        "Email": email.strip(),
        "LoginType": 0,
    }
    trade_info_params = {key: value for key, value in trade_info_params.items() if value not in ("", None)}

    plain_text = urlencode(trade_info_params)
    trade_info = _encrypt_trade_info(plain_text, hash_key=config.hash_key, hash_iv=config.hash_iv)
    trade_sha = _build_trade_sha(trade_info, hash_key=config.hash_key, hash_iv=config.hash_iv)

    return {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "order_id": order_id,
        "buyer_username": username,
        "gateway_url": config.gateway_url,
        "form_method": "POST",
        "merchant_order_no": merchant_order_no,
        "trade_info_params": trade_info_params,
        "form_fields": {
            "MerchantID": config.merchant_id,
            "TradeInfo": trade_info,
            "TradeSha": trade_sha,
            "Version": config.version,
            "EncryptType": 0,
        },
        "note": "請將 form_fields 以 HTML form POST 到 gateway_url；此為藍新 sandbox 測試資料。",
    }


def handle_callback(
    *,
    status: str,
    merchant_id: str,
    trade_info: str,
    trade_sha: str,
) -> Dict[str, Any]:
    """驗證並解密藍新支付 callback。

    目前只處理藍新 MPG 常見的 `Status/MerchantID/TradeInfo/TradeSha` 回傳格式。
    """
    config = _load_runtime_config()
    expected_sha = _build_trade_sha(trade_info, hash_key=config.hash_key, hash_iv=config.hash_iv)
    if expected_sha != trade_sha:
        raise ValueError("Invalid TradeSha.")
    if merchant_id != config.merchant_id:
        raise ValueError("MerchantID does not match configured sandbox merchant.")

    decrypted = _decrypt_trade_info(trade_info, hash_key=config.hash_key, hash_iv=config.hash_iv)
    try:
        decoded_payload = json.loads(decrypted)
    except json.JSONDecodeError:
        decoded_payload = {"raw": decrypted}

    return {
        "provider": PROVIDER_NAME,
        "mode": MODE_NAME,
        "status": status,
        "merchant_id": merchant_id,
        "trade_sha_verified": True,
        "decoded_payload": decoded_payload,
        "trade_info_base64": base64.b64encode(trade_info.encode("utf-8")).decode("ascii"),
    }
