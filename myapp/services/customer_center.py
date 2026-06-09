"""會員中心地址與發票資料服務。

這個模組專門處理會員中心與 checkout 共用的個人資料，包括：
- 地址簿
- 預設收件地址
- 發票設定

目前以 ORM 與資料庫為唯一正式資料來源。
"""

from __future__ import annotations

from typing import Any, Dict, List

from django.utils import timezone

from ..models import AppUser as AppUserModel
from ..models import UserAddress as UserAddressModel
from ..models import UserInvoiceProfile as UserInvoiceProfileModel


def _db_customer_center_enabled() -> bool:
    """判斷會員中心第一波 ORM 表是否已可用。"""
    try:
        AppUserModel.objects.count()
        return True
    except Exception:
        return False


def _get_local_user_snapshot(username: str) -> Dict[str, Any]:
    """保留舊介面的相容 hook；目前不再提供本地使用者快照。"""
    raise ValueError("User not found.")


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

    地址 id 可能因匯入、測試 seed 或歷史資料而不一致；
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
    """把 ORM 地址列轉回目前 API 使用的 payload。"""
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
    """保留舊介面的相容 hook；目前寫入流程直接更新 ORM。"""
    raise ValueError("User not found.")


def list_addresses(username: str) -> List[Dict[str, Any]]:
    """列出會員地址簿。

    回傳格式會對齊 API payload，並額外補上 `is_default`，
    讓前端地址管理頁與 checkout 能直接判斷預設地址。
    """
    db_user = _ensure_db_user(username)
    # ORM 路徑下仍維持既有 payload shape，避免前端再拆成多套格式處理。
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


def remove_address(username: str, address_id: int) -> None:
    """刪除一筆會員地址。

    如果刪除的是預設地址，會自動把剩餘第一筆地址補成新的預設值；
    若已無地址，預設地址則會清空。
    """
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


def set_default_address(username: str, address_id: int) -> Dict[str, Any]:
    """把指定地址設成會員預設地址。"""
    db_user = _ensure_db_user(username)
    db_address = db_user.addresses.filter(id=address_id).first()
    if not db_address:
        raise ValueError("Address not found.")
    if db_user.default_address_id != db_address.id:
        db_user.default_address = db_address
        db_user.save(update_fields=["default_address", "updated_at"])
    return _address_record_from_model(db_address, legacy_id_map={}, is_default=True)


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
