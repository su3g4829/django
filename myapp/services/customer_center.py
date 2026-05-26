"""買家會員中心服務模組。

集中處理地址簿與發票資料的讀寫與預設值邏輯。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from django.utils import timezone

from ..repositories import local_store


def _load_user_for_update(username: str) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    """載入 會員中心 流程中需要更新的原始資料。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        依函式用途回傳對應資料。
    """
    users = deepcopy(local_store.get_users())
    for user in users:
        if user.get("username") == username:
            user.setdefault("addresses", [])
            user.setdefault("default_address_id", None)
            user.setdefault("invoice_profile", {})
            return users, user
    raise ValueError("User not found.")


def list_addresses(username: str) -> List[Dict[str, Any]]:
    """列出 會員中心 相關資料，供頁面或 API 顯示。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    user = local_store.get_user_by_username(username) or {}
    default_id = user.get("default_address_id")
    addresses = [dict(item) for item in user.get("addresses", []) if isinstance(item, dict)]
    for address in addresses:
        address["is_default"] = address.get("id") == default_id
    return sorted(addresses, key=lambda item: (not item["is_default"], item.get("id", 0)))


def add_address(username: str, form_data: Dict[str, str]) -> Dict[str, Any]:
    """處理 會員中心 相關流程。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        form_data: 從表單或 API 送入的原始欄位資料。

    回傳:
        無回傳值；函式會直接修改 session、檔案或傳入資料。
    """
    users, user = _load_user_for_update(username)
    label = form_data.get("label", "").strip()
    recipient = form_data.get("recipient", "").strip()
    phone = form_data.get("phone", "").strip()
    city = form_data.get("city", "").strip()
    district = form_data.get("district", "").strip()
    postal_code = form_data.get("postal_code", "").strip()
    address_line = form_data.get("address_line", "").strip()
    if not all([label, recipient, phone, city, district, address_line]):
        raise ValueError("Address label, recipient, phone, city, district, and address are required.")

    addresses = user.get("addresses", [])
    next_id = max([int(item.get("id", 0)) for item in addresses] or [0]) + 1
    address = {
        "id": next_id,
        "label": label,
        "recipient": recipient,
        "phone": phone,
        "city": city,
        "district": district,
        "postal_code": postal_code,
        "address_line": address_line,
        "created_at": timezone.now().isoformat(),
    }
    addresses.append(address)
    if user.get("default_address_id") is None:
        user["default_address_id"] = next_id
    local_store.save_users(users)
    return address


def remove_address(username: str, address_id: int) -> None:
    """處理 會員中心 相關流程。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        address_id: 函式執行所需的輸入資料。

    回傳:
        無回傳值；函式會直接修改 session、檔案或傳入資料。
    """
    users, user = _load_user_for_update(username)
    addresses = user.get("addresses", [])
    next_addresses = [item for item in addresses if int(item.get("id", 0)) != address_id]
    if len(next_addresses) == len(addresses):
        raise ValueError("Address not found.")
    user["addresses"] = next_addresses
    if user.get("default_address_id") == address_id:
        user["default_address_id"] = next_addresses[0]["id"] if next_addresses else None
    local_store.save_users(users)


def set_default_address(username: str, address_id: int) -> Dict[str, Any]:
    """處理 會員中心 相關流程。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        address_id: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    users, user = _load_user_for_update(username)
    for address in user.get("addresses", []):
        if int(address.get("id", 0)) == address_id:
            user["default_address_id"] = address_id
            local_store.save_users(users)
            return address
    raise ValueError("Address not found.")


def get_default_address(username: str) -> Dict[str, Any] | None:
    """取得 會員中心 流程中指定條件的資料。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    user = local_store.get_user_by_username(username) or {}
    default_id = user.get("default_address_id")
    for address in user.get("addresses", []):
        if address.get("id") == default_id:
            return dict(address)
    return None


def get_invoice_profile(username: str) -> Dict[str, Any]:
    """取得 會員中心 流程中指定條件的資料。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    user = local_store.get_user_by_username(username) or {}
    invoice = user.get("invoice_profile", {})
    return dict(invoice) if isinstance(invoice, dict) else {}


def update_invoice_profile(username: str, form_data: Dict[str, str]) -> Dict[str, Any]:
    """更新既有 會員中心 資料。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        form_data: 從表單或 API 送入的原始欄位資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    users, user = _load_user_for_update(username)
    invoice_type = form_data.get("invoice_type", "").strip() or "personal"
    if invoice_type not in {"personal", "company"}:
        raise ValueError("Invalid invoice type.")
    invoice = {
        "invoice_type": invoice_type,
        "carrier_code": form_data.get("carrier_code", "").strip(),
        "company_name": form_data.get("company_name", "").strip(),
        "tax_id": form_data.get("tax_id", "").strip(),
        "updated_at": timezone.now().isoformat(),
    }
    if invoice_type == "company":
        if not invoice["company_name"] or not invoice["tax_id"]:
            raise ValueError("Company invoice requires company name and tax ID.")
    user["invoice_profile"] = invoice
    local_store.save_users(users)
    return invoice
