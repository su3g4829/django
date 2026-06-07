"""會員中心地址與發票資料 service。

這個模組專門處理會員中心與 checkout 會共用的個人資料，包括：
- 地址簿
- 預設收件地址
- 發票設定

目前處於 JSON 與 ORM 並行過渡期，所以每支函式都會先判斷：
- ORM 表是否可用
- 若不可用，則退回 legacy `local_store` JSON 結構
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from django.utils import timezone

from ..models import AppUser as AppUserModel
from ..models import UserAddress as UserAddressModel
from ..models import UserInvoiceProfile as UserInvoiceProfileModel
from ..repositories import local_store


def _db_customer_center_enabled() -> bool:
    """判斷會員中心第一波 ORM 表是否已可用。"""
    try:
        AppUserModel.objects.count()
        return True
    except Exception:
        return False


def _get_local_user_snapshot(username: str) -> Dict[str, Any]:
    """讀取 legacy JSON 使用者快照。

    這份資料主要在 ORM 尚未啟用或需要 fallback 時使用。
    """
    user = local_store.get_user_by_username(username)
    if not user:
        raise ValueError("User not found.")
    return dict(user)


def _ensure_db_user(username: str) -> AppUserModel:
    """取得對應的 ORM 會員列。

    會員中心的地址 / 發票寫入都以單一 `AppUser` 為主體。
    """
    user = AppUserModel.objects.filter(username=username).first()
    if user:
        return user
    raise ValueError("User not found.")


def _address_signature(address: Dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    """建立地址比對用的穩定簽名。

    JSON 與 ORM 並行時，地址 id 可能不完全一致；
    這裡用欄位組合來辨識是否為同一筆地址。
    """
    return (
        str(address.get("label") or "").strip(),
        str(address.get("recipient") or "").strip(),
        str(address.get("phone") or "").strip(),
        str(address.get("city") or "").strip(),
        str(address.get("district") or "").strip(),
        str(address.get("postal_code") or "").strip(),
        str(address.get("address_line") or "").strip(),
    )


def _address_record_from_model(
    address: UserAddressModel,
    *,
    legacy_id_map: Dict[tuple[str, str, str, str, str, str, str], int],
    is_default: bool,
) -> Dict[str, Any]:
    """把 ORM 地址列轉回 API / legacy 共用的 payload。"""
    payload = {
        "id": legacy_id_map.get(
            _address_signature(
                {
                    "label": address.label,
                    "recipient": address.recipient,
                    "phone": address.phone,
                    "city": address.city,
                    "district": address.district,
                    "postal_code": address.postal_code,
                    "address_line": address.address_line,
                }
            ),
            address.id,
        ),
        "label": address.label,
        "recipient": address.recipient,
        "phone": address.phone,
        "city": address.city,
        "district": address.district,
        "postal_code": address.postal_code,
        "address_line": address.address_line,
        "created_at": address.created_at.isoformat() if address.created_at else "",
        "is_default": is_default,
    }
    return payload


def _load_user_for_update(username: str) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    """載入 legacy JSON 使用者資料，供寫入流程更新。

    回傳兩份資料：
    - 完整 `users` 清單：最後寫回 `local_store` 需要用
    - 目前目標使用者 dict：方便直接修改地址或發票欄位
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
    """列出會員地址簿。

    回傳格式會對齊 API payload，並額外補上 `is_default`，
    讓前端地址管理頁與 checkout 能直接判斷預設地址。
    """
    if not _db_customer_center_enabled():
        user = _get_local_user_snapshot(username)
        default_id = user.get("default_address_id")
        addresses = [dict(item) for item in user.get("addresses", []) if isinstance(item, dict)]
        for address in addresses:
            address["is_default"] = address.get("id") == default_id
        return sorted(addresses, key=lambda item: (not item["is_default"], item.get("id", 0)))

    db_user = _ensure_db_user(username)
    # ORM 路徑下仍維持 legacy payload shape，避免前端在遷移期需要分兩套處理。
    serialized = [
        _address_record_from_model(
            address,
            legacy_id_map={},
            is_default=address.id == db_user.default_address_id,
        )
        for address in db_user.addresses.all().order_by("id")
    ]
    return sorted(serialized, key=lambda item: (not item["is_default"], item.get("id", 0)))


def add_address(username: str, form_data: Dict[str, str]) -> Dict[str, Any]:
    """新增一筆會員地址。

    基本規則：
    - 必填欄位缺漏時直接丟 `ValueError`
    - 若會員還沒有預設地址，第一筆新增的地址會自動成為預設值
    """
    label = form_data.get("label", "").strip()
    recipient = form_data.get("recipient", "").strip()
    phone = form_data.get("phone", "").strip()
    city = form_data.get("city", "").strip()
    district = form_data.get("district", "").strip()
    postal_code = form_data.get("postal_code", "").strip()
    address_line = form_data.get("address_line", "").strip()
    if not all([label, recipient, phone, city, district, address_line]):
        raise ValueError("Address label, recipient, phone, city, district, and address are required.")

    if _db_customer_center_enabled():
        db_user = _ensure_db_user(username)
        db_address = UserAddressModel.objects.create(
            user=db_user,
            label=label,
            recipient=recipient,
            phone=phone,
            city=city,
            district=district,
            postal_code=postal_code,
            address_line=address_line,
        )
        if db_user.default_address_id is None:
            db_user.default_address = db_address
            db_user.save(update_fields=["default_address", "updated_at"])
        return _address_record_from_model(
            db_address,
            legacy_id_map={},
            is_default=db_user.default_address_id == db_address.id,
        )

    users, user = _load_user_for_update(username)
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
    """刪除一筆會員地址。

    如果刪除的是預設地址，會自動把剩餘第一筆地址補成新的預設值；
    若已無地址，預設地址則會清空。
    """
    if _db_customer_center_enabled():
        db_user = _ensure_db_user(username)
        db_address = db_user.addresses.filter(id=address_id).first()
        if not db_address:
            raise ValueError("Address not found.")
        was_default = db_user.default_address_id == db_address.id
        db_address.delete()
        db_user.refresh_from_db()
        if was_default:
            next_default = db_user.addresses.order_by("id").first()
            db_user.default_address = next_default
            db_user.save(update_fields=["default_address", "updated_at"])
        return

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
    """把指定地址設成會員預設地址。"""
    if _db_customer_center_enabled():
        db_user = _ensure_db_user(username)
        db_address = db_user.addresses.filter(id=address_id).first()
        if not db_address:
            raise ValueError("Address not found.")
        if db_user.default_address_id != db_address.id:
            db_user.default_address = db_address
            db_user.save(update_fields=["default_address", "updated_at"])
        return _address_record_from_model(db_address, legacy_id_map={}, is_default=True)

    users, user = _load_user_for_update(username)
    for address in user.get("addresses", []):
        if int(address.get("id", 0)) == address_id:
            user["default_address_id"] = address_id
            local_store.save_users(users)
            return address
    raise ValueError("Address not found.")


def get_default_address(username: str) -> Dict[str, Any] | None:
    """取得會員目前的預設地址。

    若尚未設定任何地址，回傳 `None`。
    """
    for address in list_addresses(username):
        if address.get("is_default"):
            return dict(address)
    return None


def get_address_by_id(username: str, address_id: int) -> Dict[str, Any] | None:
    """依地址 ID 取得單筆地址資料。"""
    for address in list_addresses(username):
        if int(address.get("id", 0)) == address_id:
            return dict(address)
    return None


def get_invoice_profile(username: str) -> Dict[str, Any]:
    """取得會員發票設定。

    這份資料會被：
    - 會員中心發票頁
    - checkout 發票摘要區塊
    直接重用。
    """
    if not _db_customer_center_enabled():
        user = _get_local_user_snapshot(username)
        invoice = user.get("invoice_profile", {})
        return dict(invoice) if isinstance(invoice, dict) else {}

    db_user = _ensure_db_user(username)
    profile = UserInvoiceProfileModel.objects.filter(user=db_user).first()
    if not profile:
        return {}
    return {
        "invoice_type": profile.invoice_type,
        "carrier_code": profile.carrier_code,
        "company_name": profile.company_name,
        "tax_id": profile.tax_id,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else "",
    }


def update_invoice_profile(username: str, form_data: Dict[str, str]) -> Dict[str, Any]:
    """更新會員發票設定。

    規則：
    - `invoice_type` 只接受 `personal` 或 `company`
    - 公司發票必須同時提供公司名稱與統編
    """
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

    if _db_customer_center_enabled():
        db_user = _ensure_db_user(username)
        profile, _ = UserInvoiceProfileModel.objects.update_or_create(
            user=db_user,
            defaults={
                "invoice_type": invoice["invoice_type"],
                "carrier_code": invoice["carrier_code"],
                "company_name": invoice["company_name"],
                "tax_id": invoice["tax_id"],
            },
        )
        return {
            "invoice_type": profile.invoice_type,
            "carrier_code": profile.carrier_code,
            "company_name": profile.company_name,
            "tax_id": profile.tax_id,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else "",
        }

    users, user = _load_user_for_update(username)
    user["invoice_profile"] = invoice
    local_store.save_users(users)
    return invoice
