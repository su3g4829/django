"""本地 JSON 版示範會員系統。

這一層刻意不依賴 Django ORM，讓專案在未導入資料庫前仍可提供：

- 註冊 / 登入 / 登出
- 角色與賣家申請
- 帳號停權
- session 使用者快照

同時會保留未來轉移到 `django.contrib.auth` 需要的欄位，
例如 `created_at`、`updated_at`、`last_login_at`、`seller_requested_at`。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.db import models
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from ..models import AppUser as AppUserModel
from ..models import SellerRequest as SellerRequestModel
from ..models import UserShippingRule as UserShippingRuleModel
from ..repositories import local_store

# 會員系統目前仍在 JSON -> ORM 過渡期。
# 這個 service 統一處理註冊、登入、賣家申請、帳號狀態與 session 同步。
SESSION_USER_KEY = "demo_user"
SELLER_REQUEST_PENDING = "pending"
SELLER_REQUEST_REJECTED = "rejected"
SELLER_REQUEST_APPROVED = "approved"
ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_SUSPENDED = "suspended"
ADMIN_ROLES = {"admin", "staff"}
SELLER_ROLES = {"seller", "admin", "staff"}

DEFAULT_SHIPPING_RULES = {
    "home_delivery_enabled": True,
    "home_delivery_fee": "80.00",
    "convenience_store_enabled": True,
    "convenience_store_fee": "60.00",
    "free_shipping_threshold": "1200.00",
}


def _db_auth_enabled() -> bool:
    # ORM user 表可用時，auth 與 profile 相關流程就優先走資料庫版本。
    """Return True when the first-wave ORM auth tables are available."""
    try:
        AppUserModel.objects.count()
        return True
    except Exception:
        return False


def _parse_dt(value: Any):
    # 舊 JSON 時間欄位常是 ISO 字串，寫回 ORM 前先做寬鬆轉換。
    """Convert legacy ISO strings into datetimes when possible."""
    if not value:
        return None
    if hasattr(value, "tzinfo"):
        return value
    return parse_datetime(str(value))


def _dt_to_iso(value: Any) -> str:
    # API 與 session 快照一律輸出字串格式時間，減少前端型別分支。
    """Convert datetimes or nullable timestamp fields into stable API strings."""
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _sync_user_to_orm(user: Dict[str, Any]) -> None:
    # JSON / ORM 並行期，這裡把單筆舊資料同步到新表，包含運費規則與賣家申請狀態。
    """Mirror one legacy JSON user snapshot into the ORM user tables."""
    if not _db_auth_enabled():
        return
    username = str(user.get("username") or "").strip().lower()
    if not username:
        return
    email = str(user.get("email") or "").strip().lower() or f"{username}@seed.local"
    password_hash = str(user.get("password_hash") or "").strip()
    if not password_hash:
        legacy_password = str(user.get("password") or "").strip()
        if legacy_password:
            password_hash = make_password(legacy_password)
    db_user, _ = AppUserModel.objects.update_or_create(
        username=username,
        defaults={
            "email": email,
            "password_hash": password_hash,
            "display_name": str(user.get("display_name") or username),
            "role": str(user.get("role") or "member"),
            "account_status": str(user.get("account_status") or ACCOUNT_STATUS_ACTIVE),
            "seller_request_status": str(user.get("seller_request_status") or "none"),
            "last_login_at": _parse_dt(user.get("last_login_at")),
            "seller_requested_at": _parse_dt(user.get("seller_requested_at")),
            "seller_reviewed_at": _parse_dt(user.get("seller_reviewed_at")),
            "account_status_updated_at": _parse_dt(user.get("account_status_updated_at")),
        },
    )
    shipping_rules = _normalize_shipping_rules(user.get("shipping_rules"))
    UserShippingRuleModel.objects.update_or_create(
        user=db_user,
        defaults={
            "home_delivery_enabled": bool(shipping_rules["home_delivery_enabled"]),
            "home_delivery_fee": shipping_rules["home_delivery_fee"],
            "convenience_store_enabled": bool(shipping_rules["convenience_store_enabled"]),
            "convenience_store_fee": shipping_rules["convenience_store_fee"],
            "free_shipping_threshold": shipping_rules["free_shipping_threshold"],
        },
    )
    seller_status = str(user.get("seller_request_status") or "none")
    if seller_status != "none":
        SellerRequestModel.objects.filter(user=db_user, is_current=True).update(is_current=False)
        SellerRequestModel.objects.update_or_create(
            user=db_user,
            status=seller_status,
            is_current=True,
            defaults={
                "reviewed_at": _parse_dt(user.get("seller_reviewed_at")),
                "reviewed_by": None,
                "note": "",
            },
        )
    else:
        SellerRequestModel.objects.filter(user=db_user, is_current=True).update(is_current=False)


def _get_or_bootstrap_db_user(username: str) -> Optional[AppUserModel]:
    # 這裡只讀 ORM 既有帳號，不在登入流程中隱性建立新會員。
    """Return one ORM user row when database-backed auth is enabled."""
    clean_username = str(username or "").strip().lower()
    if not clean_username or not _db_auth_enabled():
        return None
    return AppUserModel.objects.filter(username=clean_username).first()


def _db_user_to_record(db_user: AppUserModel) -> Dict[str, Any]:
    # ORM user 轉成舊有 payload 形狀，讓上層 API 不必知道資料來源差異。
    """Serialize an ORM user row into the legacy auth/profile payload shape."""
    return {
        "id": db_user.id,
        "username": db_user.username,
        "display_name": db_user.display_name or db_user.username,
        "role": db_user.role or "member",
        "account_status": db_user.account_status or ACCOUNT_STATUS_ACTIVE,
        "seller_request_status": db_user.seller_request_status or "",
        "email": db_user.email or "",
        "created_at": _dt_to_iso(db_user.created_at),
        "updated_at": _dt_to_iso(db_user.updated_at),
        "last_login_at": _dt_to_iso(db_user.last_login_at),
        "seller_requested_at": _dt_to_iso(db_user.seller_requested_at),
        "seller_reviewed_at": _dt_to_iso(db_user.seller_reviewed_at),
        "account_status_updated_at": _dt_to_iso(db_user.account_status_updated_at),
    }


def _user_snapshot(user: Dict[str, Any]) -> Dict[str, Any]:
    # session 只保存前端目前會用到的穩定欄位，避免把整個 user record 都塞進去。
    """建立可安全放入 session 與 API 回應的會員快照。"""
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
        "role": user.get("role", "member"),
        "account_status": user.get("account_status", ACCOUNT_STATUS_ACTIVE),
        "seller_request_status": user.get("seller_request_status", ""),
        "email": user.get("email", ""),
        "created_at": user.get("created_at", ""),
        "updated_at": user.get("updated_at", ""),
        "last_login_at": user.get("last_login_at", ""),
        "seller_requested_at": user.get("seller_requested_at", ""),
        "seller_reviewed_at": user.get("seller_reviewed_at", ""),
        "shipping_rules": get_seller_shipping_rules(user["username"]),
    }


def _normalize_shipping_rules(shipping_rules: Dict[str, Any] | None = None) -> Dict[str, Any]:
    # 賣家運費規則所有入口都先補預設值，避免缺欄位時前端要自行兜底。
    rules = dict(DEFAULT_SHIPPING_RULES)
    if isinstance(shipping_rules, dict):
        rules.update(shipping_rules)
    return {
        "home_delivery_enabled": bool(rules.get("home_delivery_enabled", True)),
        "home_delivery_fee": str(rules.get("home_delivery_fee", "80.00")),
        "convenience_store_enabled": bool(rules.get("convenience_store_enabled", True)),
        "convenience_store_fee": str(rules.get("convenience_store_fee", "60.00")),
        "free_shipping_threshold": str(rules.get("free_shipping_threshold", "1200.00")),
    }


def _shipping_rules_from_model(rules: UserShippingRuleModel) -> Dict[str, Any]:
    # ORM 運費規則 row 轉回前端熟悉的 dict 結構。
    """Serialize ORM shipping-rule rows back into the legacy API payload shape."""
    return _normalize_shipping_rules(
        {
            "home_delivery_enabled": bool(rules.home_delivery_enabled),
            "home_delivery_fee": str(rules.home_delivery_fee),
            "convenience_store_enabled": bool(rules.convenience_store_enabled),
            "convenience_store_fee": str(rules.convenience_store_fee),
            "free_shipping_threshold": str(rules.free_shipping_threshold),
        }
    )


def _is_hashed_password(value: str) -> bool:
    # 舊帳號資料可能混有明碼與 Django hash，先辨識目前是哪一種格式。
    """判斷字串是否為 Django password hasher 產生的值。"""
    try:
        identify_hasher(value)
        return True
    except Exception:
        return False


def _save_user_patch(username: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # JSON fallback 模式下，集中處理單筆使用者局部更新。
    """更新單一會員欄位並寫回 JSON。"""
    users = deepcopy(local_store.get_users())
    for item in users:
        if item.get("username") != username:
            continue
        item.update(patch)
        local_store.save_users(users)
        return local_store.get_user_by_username(username)
    return None


def _persist_user_record(record: Dict[str, Any]) -> Dict[str, Any]:
    # 寫回舊 payload 時順手補齊地址、發票、運費規則等欄位，避免後續讀取缺 key。
    """Persist one legacy-shaped user record into JSON, appending when absent."""
    clean_username = str(record.get("username") or "").strip().lower()
    payload = deepcopy(record)
    payload["username"] = clean_username
    payload.setdefault("addresses", [])
    payload.setdefault("default_address_id", None)
    payload.setdefault("invoice_profile", {})
    payload.setdefault("shipping_rules", _normalize_shipping_rules(payload.get("shipping_rules")))
    payload.setdefault("password_hash", "")
    payload.setdefault("email", "")
    payload.setdefault("role", "member")
    payload.setdefault("account_status", ACCOUNT_STATUS_ACTIVE)
    payload.setdefault("seller_request_status", "")
    if _db_auth_enabled():
        return payload

    users = deepcopy(local_store.get_users())

    for index, item in enumerate(users):
        if str(item.get("username") or "").strip().lower() != clean_username:
            continue
        existing = deepcopy(item)
        existing.update(payload)
        users[index] = existing
        local_store.save_users(users)
        return local_store.get_user_by_username(clean_username) or existing

    users.append(payload)
    local_store.save_users(users)
    return local_store.get_user_by_username(clean_username) or payload


def _upgrade_legacy_password(user: Dict[str, Any], raw_password: str) -> None:
    # 使用者若仍以舊明碼密碼登入，成功後立刻升級成 Django password hash。
    """若舊資料仍保存明文密碼，首次登入時升級成 hash。"""
    patched = deepcopy(user)
    patched["password_hash"] = make_password(raw_password)
    patched.pop("password", None)
    patched["updated_at"] = timezone.now().isoformat()
    if _db_auth_enabled():
        _sync_user_to_orm(patched)
        return
    users = deepcopy(local_store.get_users())
    for item in users:
        if item.get("username") != user["username"]:
            continue
        item["password_hash"] = patched["password_hash"]
        item.pop("password", None)
        item["updated_at"] = patched["updated_at"]
        local_store.save_users(users)
        _sync_user_to_orm(item)
        return


def _mark_login(username: str) -> Optional[Dict[str, Any]]:
    # 更新最後登入時間，並回傳最新 canonical user payload 給 session 寫入。
    """記錄最後登入時間，方便未來轉資料庫。"""
    now = timezone.now().isoformat()
    if _db_auth_enabled():
        AppUserModel.objects.filter(username=username).update(last_login_at=_parse_dt(now))
        db_user = _get_or_bootstrap_db_user(username)
        if db_user:
            db_user.refresh_from_db()
            return {
                **_db_user_to_record(db_user),
                "shipping_rules": get_seller_shipping_rules(username),
            }
        return None
    updated = _save_user_patch(username, {"last_login_at": now, "updated_at": now})
    if updated:
        _sync_user_to_orm(updated)
    return updated


def is_admin(user: Dict[str, Any] | None) -> bool:
    # 管理後台與 staff-only API 共用這個角色判斷。
    """判斷目前會員是否具備管理員角色。"""
    return bool(user and user.get("role") in ADMIN_ROLES)


def is_seller(user: Dict[str, Any] | None) -> bool:
    # seller、admin、staff 都視為具備賣家權限。
    """判斷目前會員是否具備賣家角色。"""
    return bool(user and user.get("role") in SELLER_ROLES)


def is_active(user: Dict[str, Any] | None) -> bool:
    # 已停權帳號即使還有 session，也不應通過需要登入的操作。
    """判斷目前會員是否為可使用中的帳號。"""
    return bool(user and user.get("account_status", ACCOUNT_STATUS_ACTIVE) == ACCOUNT_STATUS_ACTIVE)


def authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    # 登入優先驗證 ORM 帳號；若仍在 JSON-only 模式，則兼容 hash 與舊明碼密碼。
    """驗證會員帳密，成功時回傳 session 用使用者快照。"""
    clean_username = username.strip().lower()
    db_enabled = _db_auth_enabled()
    db_user = _get_or_bootstrap_db_user(clean_username) if db_enabled else None
    user = None if db_enabled else local_store.get_user_by_username(clean_username)

    if db_user and db_user.account_status != ACCOUNT_STATUS_ACTIVE:
        return None
    if user and user.get("account_status", ACCOUNT_STATUS_ACTIVE) != ACCOUNT_STATUS_ACTIVE:
        return None

    if db_user and str(db_user.password_hash or "").strip():
        if check_password(password, db_user.password_hash):
            now = timezone.now()
            db_user.last_login_at = now
            db_user.save(update_fields=["last_login_at", "updated_at"])
            db_user.refresh_from_db()
            return _user_snapshot(
                {
                    **_db_user_to_record(db_user),
                    "shipping_rules": get_seller_shipping_rules(clean_username),
                }
            )

    if db_enabled:
        return None

    if not user:
        return None

    password_hash = str(user.get("password_hash", "")).strip()
    if password_hash and _is_hashed_password(password_hash):
        if not check_password(password, password_hash):
            return None
        refreshed = _mark_login(clean_username) or user
        return _user_snapshot(refreshed)

    legacy_password = str(user.get("password", ""))
    if legacy_password != password:
        return None

    _upgrade_legacy_password(user, password)
    refreshed = _mark_login(clean_username) or local_store.get_user_by_username(clean_username) or user
    return _user_snapshot(refreshed)


def register_user(username: str, display_name: str, password: str, email: str = "") -> Dict[str, Any]:
    # 註冊後回傳可直接寫入 session 的 user snapshot，避免 view 再重組一次資料。
    """建立新會員資料並回傳 session 用快照。"""
    clean_username = username.strip().lower()
    clean_display_name = display_name.strip()
    clean_email = email.strip().lower()
    if not clean_username:
        raise ValueError("Username is required.")
    if len(clean_username) < 3:
        raise ValueError("Username must be at least 3 characters.")
    if not clean_username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Username may only use letters, numbers, hyphens, and underscores.")
    if not _db_auth_enabled() and local_store.get_user_by_username(clean_username):
        raise ValueError("This username is already taken.")
    if _db_auth_enabled():
        if AppUserModel.objects.filter(username=clean_username).exists():
            raise ValueError("This username is already taken.")
        if clean_email and AppUserModel.objects.filter(email=clean_email).exists():
            raise ValueError("This email is already taken.")
    if not clean_display_name:
        raise ValueError("Display name is required.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    now = timezone.now().isoformat()
    user = {
        "username": clean_username,
        "display_name": clean_display_name,
        "password_hash": make_password(password),
        "role": "member",
        "account_status": ACCOUNT_STATUS_ACTIVE,
        "seller_request_status": "",
        "email": clean_email,
        "addresses": [],
        "default_address_id": None,
        "invoice_profile": {},
        "created_at": now,
        "updated_at": now,
        "last_login_at": "",
        "seller_requested_at": "",
        "seller_reviewed_at": "",
        "account_status_updated_at": "",
    }
    if _db_auth_enabled():
        db_user = AppUserModel.objects.create(
            username=clean_username,
            email=clean_email or f"{clean_username}@seed.local",
            password_hash=user["password_hash"],
            display_name=clean_display_name,
            role="member",
            account_status=ACCOUNT_STATUS_ACTIVE,
            seller_request_status="none",
        )
        UserShippingRuleModel.objects.get_or_create(
            user=db_user,
            defaults={
                "home_delivery_enabled": bool(DEFAULT_SHIPPING_RULES["home_delivery_enabled"]),
                "home_delivery_fee": DEFAULT_SHIPPING_RULES["home_delivery_fee"],
                "convenience_store_enabled": bool(DEFAULT_SHIPPING_RULES["convenience_store_enabled"]),
                "convenience_store_fee": DEFAULT_SHIPPING_RULES["convenience_store_fee"],
                "free_shipping_threshold": DEFAULT_SHIPPING_RULES["free_shipping_threshold"],
            },
        )
        return _user_snapshot(
            {
                **_db_user_to_record(db_user),
                "password_hash": user["password_hash"],
                "shipping_rules": get_seller_shipping_rules(clean_username),
                "addresses": [],
                "default_address_id": None,
                "invoice_profile": {},
            }
        )

    users = deepcopy(local_store.get_users())
    next_id = max([int(item.get("id", 0)) for item in users] or [0]) + 1
    user["id"] = next_id
    users.append(user)
    local_store.save_users(users)
    return _user_snapshot(user)


def update_profile(username: str, display_name: str, new_password: str = "", email: str = "") -> Dict[str, Any]:
    # 會員中心編輯資料集中在這裡，包含 display name、email 與可選的新密碼。
    """更新會員顯示名稱、密碼與信箱。"""
    clean_username = username.strip().lower()
    clean_display_name = display_name.strip()
    clean_email = email.strip().lower()
    if not clean_display_name:
        raise ValueError("Display name is required.")
    if new_password and len(new_password) < 6:
        raise ValueError("New password must be at least 6 characters.")
    if _db_auth_enabled() and clean_email:
        email_owner = AppUserModel.objects.filter(email=clean_email).exclude(username=clean_username).exists()
        if email_owner:
            raise ValueError("This email is already taken.")

    if _db_auth_enabled():
        db_user = _get_or_bootstrap_db_user(clean_username)
        if db_user:
            db_user.display_name = clean_display_name
            db_user.email = clean_email
            if new_password:
                db_user.password_hash = make_password(new_password)
            db_user.save()
            return _user_snapshot(
                {
                    **_db_user_to_record(db_user),
                    "password_hash": db_user.password_hash,
                    "shipping_rules": get_seller_shipping_rules(clean_username),
                }
            )
        raise ValueError("User not found.")
    users = deepcopy(local_store.get_users())
    for item in users:
        if item.get("username") != clean_username:
            continue
        item["display_name"] = clean_display_name
        item["email"] = clean_email
        item["updated_at"] = timezone.now().isoformat()
        if new_password:
            item["password_hash"] = make_password(new_password)
            item.pop("password", None)
        local_store.save_users(users)
        return _user_snapshot(item)
    raise ValueError("User not found.")


def get_seller_shipping_rules(username: str) -> Dict[str, Any]:
    # 商品運費與結帳運費計算都依賴這份規則；若 ORM 尚未有資料，這裡會補建預設值。
    """Return seller-level shipping rules with normalized defaults."""
    clean_username = username.strip().lower()
    if _db_auth_enabled():
        db_user = _get_or_bootstrap_db_user(clean_username)
        if db_user:
            db_rules = UserShippingRuleModel.objects.filter(user=db_user).first()
            if db_rules:
                return _shipping_rules_from_model(db_rules)
            db_rules = UserShippingRuleModel.objects.create(
                user=db_user,
                home_delivery_enabled=bool(DEFAULT_SHIPPING_RULES["home_delivery_enabled"]),
                home_delivery_fee=DEFAULT_SHIPPING_RULES["home_delivery_fee"],
                convenience_store_enabled=bool(DEFAULT_SHIPPING_RULES["convenience_store_enabled"]),
                convenience_store_fee=DEFAULT_SHIPPING_RULES["convenience_store_fee"],
                free_shipping_threshold=DEFAULT_SHIPPING_RULES["free_shipping_threshold"],
            )
            return _shipping_rules_from_model(db_rules)
        raise ValueError("User not found.")
    user = local_store.get_user_by_username(clean_username)
    if not user:
        raise ValueError("User not found.")
    return _normalize_shipping_rules(user.get("shipping_rules"))


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    # 其他 service 需要查會員資料時，統一從這裡拿標準化後的快照。
    """Return one canonical user snapshot by username, preferring ORM when available."""
    clean_username = str(username or "").strip().lower()
    if not clean_username:
        return None
    if _db_auth_enabled():
        db_user = _get_or_bootstrap_db_user(clean_username)
        if db_user:
            return _user_snapshot(
                {
                    **_db_user_to_record(db_user),
                    "shipping_rules": get_seller_shipping_rules(clean_username),
                }
            )
        return None
    user = local_store.get_user_by_username(clean_username)
    if not user:
        return None
    return _user_snapshot(user)


def update_seller_shipping_rules(
    username: str,
    *,
    home_delivery_enabled: bool,
    home_delivery_fee: str,
    convenience_store_enabled: bool,
    convenience_store_fee: str,
    free_shipping_threshold: str,
) -> Dict[str, Any]:
    # 賣家運費設定在寫入前先完成欄位與金額驗證，避免商品與訂單流程吃到非法值。
    """Persist seller-level shipping rules."""
    if not home_delivery_enabled and not convenience_store_enabled:
        raise ValueError("At least one shipping method must stay enabled.")

    def _clean_amount(raw: str, field_label: str) -> str:
        value = str(raw).strip()
        if not value:
            raise ValueError(f"{field_label} is required.")
        try:
            amount = float(value)
        except ValueError:
            raise ValueError(f"{field_label} must be a valid number.") from None
        if amount < 0:
            raise ValueError(f"{field_label} cannot be negative.")
        return f"{amount:.2f}"

    rules = {
        "home_delivery_enabled": bool(home_delivery_enabled),
        "home_delivery_fee": _clean_amount(home_delivery_fee, "Home-delivery fee"),
        "convenience_store_enabled": bool(convenience_store_enabled),
        "convenience_store_fee": _clean_amount(convenience_store_fee, "Convenience-store fee"),
        "free_shipping_threshold": _clean_amount(free_shipping_threshold, "Free-shipping threshold"),
    }
    clean_username = username.strip().lower()
    db_rules = None
    if _db_auth_enabled():
        db_user = _get_or_bootstrap_db_user(clean_username)
        if db_user:
            db_rules, _ = UserShippingRuleModel.objects.update_or_create(
                user=db_user,
                defaults={
                    "home_delivery_enabled": bool(rules["home_delivery_enabled"]),
                    "home_delivery_fee": rules["home_delivery_fee"],
                    "convenience_store_enabled": bool(rules["convenience_store_enabled"]),
                    "convenience_store_fee": rules["convenience_store_fee"],
                    "free_shipping_threshold": rules["free_shipping_threshold"],
                },
            )
            return _shipping_rules_from_model(db_rules)
        raise ValueError("User not found.")
    updated = _save_user_patch(
        clean_username,
        {
            "shipping_rules": rules,
            "updated_at": timezone.now().isoformat(),
        },
    )
    if not updated:
        raise ValueError("User not found.")
    return _normalize_shipping_rules(updated.get("shipping_rules"))


def request_seller_role(username: str) -> Dict[str, Any]:
    # 一般會員送出賣家申請後，狀態會切成 pending，等待管理端審核。
    """提出賣家資格申請。"""
    clean_username = username.strip().lower()
    if _db_auth_enabled():
        db_user = _get_or_bootstrap_db_user(clean_username)
        if db_user:
            if db_user.role in SELLER_ROLES:
                raise ValueError("You already have seller access.")
            now = timezone.now()
            db_user.seller_request_status = SELLER_REQUEST_PENDING
            db_user.seller_requested_at = now
            db_user.save()
            SellerRequestModel.objects.filter(user=db_user, is_current=True).update(is_current=False)
            SellerRequestModel.objects.update_or_create(
                user=db_user,
                status=SELLER_REQUEST_PENDING,
                is_current=True,
                defaults={"reviewed_at": None, "reviewed_by": None, "note": ""},
            )
            return _user_snapshot(
                {
                    **_db_user_to_record(db_user),
                    "shipping_rules": get_seller_shipping_rules(clean_username),
                }
            )
        raise ValueError("User not found.")
    users = deepcopy(local_store.get_users())
    for item in users:
        if item.get("username") != clean_username:
            continue
        if item.get("role") in SELLER_ROLES:
            raise ValueError("You already have seller access.")
        now = timezone.now().isoformat()
        item["seller_request_status"] = SELLER_REQUEST_PENDING
        item["seller_requested_at"] = now
        item["updated_at"] = now
        local_store.save_users(users)
        _sync_user_to_orm(item)
        return _user_snapshot(item)
    raise ValueError("User not found.")


def list_seller_requests() -> list[Dict[str, Any]]:
    # 管理端審核頁只需要待審申請，依申請時間倒序列出。
    """列出待審核的賣家申請。"""
    if _db_auth_enabled():
        db_requests = list(
            AppUserModel.objects.filter(seller_request_status=SELLER_REQUEST_PENDING).order_by("-seller_requested_at", "username")
        )
        return [_db_user_to_record(item) for item in db_requests]
    requests = [user for user in local_store.get_users() if user.get("seller_request_status") == SELLER_REQUEST_PENDING]
    return sorted(requests, key=lambda item: item.get("seller_requested_at", ""), reverse=True)


def review_seller_request(username: str, approved: bool) -> Dict[str, Any]:
    # 審核通過會直接升成 seller；駁回則保留原角色，只更新申請狀態。
    """審核賣家申請。"""
    clean_username = username.strip().lower()
    if _db_auth_enabled():
        db_user = _get_or_bootstrap_db_user(clean_username)
        if db_user:
            now = timezone.now()
            db_user.seller_reviewed_at = now
            if approved:
                db_user.role = "seller"
                db_user.seller_request_status = SELLER_REQUEST_APPROVED
            else:
                db_user.seller_request_status = SELLER_REQUEST_REJECTED
            db_user.save()
            SellerRequestModel.objects.filter(user=db_user, is_current=True).update(is_current=False)
            SellerRequestModel.objects.update_or_create(
                user=db_user,
                status=db_user.seller_request_status,
                is_current=True,
                defaults={"reviewed_at": now, "reviewed_by": None, "note": ""},
            )
            return _user_snapshot(
                {
                    **_db_user_to_record(db_user),
                    "shipping_rules": get_seller_shipping_rules(clean_username),
                }
            )
        raise ValueError("User not found.")
    users = deepcopy(local_store.get_users())
    for item in users:
        if item.get("username") != clean_username:
            continue
        now = timezone.now().isoformat()
        item["seller_reviewed_at"] = now
        item["updated_at"] = now
        if approved:
            item["role"] = "seller"
            item["seller_request_status"] = SELLER_REQUEST_APPROVED
        else:
            item["seller_request_status"] = SELLER_REQUEST_REJECTED
        local_store.save_users(users)
        _sync_user_to_orm(item)
        return _user_snapshot(item)
    raise ValueError("User not found.")


def list_users(search: str = "", role: str = "", account_status: str = "") -> list[Dict[str, Any]]:
    # 會員管理總表支援關鍵字、角色與帳號狀態篩選。
    """查詢會員清單。"""
    search_value = search.strip().lower()
    role_value = role.strip().lower()
    status_value = account_status.strip().lower()
    if _db_auth_enabled():
        queryset = AppUserModel.objects.all()
        if search_value:
            queryset = queryset.filter(
                models.Q(username__icontains=search_value) | models.Q(display_name__icontains=search_value)
            )
        if role_value:
            queryset = queryset.filter(role=role_value)
        if status_value:
            queryset = queryset.filter(account_status=status_value)
        db_users = list(queryset.order_by("role", "username"))
        return [_db_user_to_record(user) for user in db_users]
    users: list[Dict[str, Any]] = []
    for user in local_store.get_users():
        if search_value and search_value not in str(user.get("username", "")).lower() and search_value not in str(user.get("display_name", "")).lower():
            continue
        if role_value and str(user.get("role", "")).lower() != role_value:
            continue
        if status_value and str(user.get("account_status", ACCOUNT_STATUS_ACTIVE)).lower() != status_value:
            continue
        users.append(user)
    return sorted(users, key=lambda item: (item.get("role", ""), item.get("username", "")))


def update_account_status(username: str, account_status: str) -> Dict[str, Any]:
    # 帳號狀態目前只允許 active / suspended 兩種，並同步記錄狀態變更時間。
    """更新會員帳號狀態。"""
    clean_username = username.strip().lower()
    clean_status = account_status.strip().lower()
    if clean_status not in {ACCOUNT_STATUS_ACTIVE, ACCOUNT_STATUS_SUSPENDED}:
        raise ValueError("Invalid account status.")
    if _db_auth_enabled():
        db_user = _get_or_bootstrap_db_user(clean_username)
        if db_user:
            now = timezone.now()
            db_user.account_status = clean_status
            db_user.account_status_updated_at = now
            db_user.save()
            return _user_snapshot(
                {
                    **_db_user_to_record(db_user),
                    "shipping_rules": get_seller_shipping_rules(clean_username),
                }
            )
        raise ValueError("User not found.")
    users = deepcopy(local_store.get_users())
    for item in users:
        if item.get("username") != clean_username:
            continue
        now = timezone.now().isoformat()
        item["account_status"] = clean_status
        item["account_status_updated_at"] = now
        item["updated_at"] = now
        local_store.save_users(users)
        _sync_user_to_orm(item)
        return _user_snapshot(item)
    raise ValueError("User not found.")


def login(session, user: Dict[str, Any]) -> None:
    # 登入時除了寫 session user，也要把 guest cart 與 guest personalization 合併到會員資料。
    """將會員快照寫入 session，並同步更新登入時間。"""
    from . import cart, personalization

    refreshed = _mark_login(str(user["username"]))
    cart.migrate_guest_cart(session, str(user["username"]))
    personalization.migrate_guest_buckets(session, str(user["username"]))
    session[SESSION_USER_KEY] = _user_snapshot(refreshed or user)
    session.modified = True


def logout(session) -> None:
    # 登出前順手清理 guest bucket，避免下一位匿名訪客沿用舊暫存資料。
    """清除目前 session 的會員資訊。"""
    from . import cart, personalization

    cart.clear_guest_cart(session)
    personalization.clear_guest_buckets(session)
    session.pop(SESSION_USER_KEY, None)
    session.modified = True


def get_current_user(session) -> Optional[Dict[str, Any]]:
    # 每次讀目前登入者都重新和資料源比對，確保權限、停權狀態與運費規則是最新的。
    """從 session 取回目前登入會員，並與 JSON 最新資料同步。"""
    user = session.get(SESSION_USER_KEY)
    if not isinstance(user, dict):
        return None
    username = user.get("username")
    if not username:
        return None
    if _db_auth_enabled():
        db_user = _get_or_bootstrap_db_user(str(username))
        if db_user:
            if db_user.account_status != ACCOUNT_STATUS_ACTIVE:
                logout(session)
                return None
            fresh_user = _user_snapshot(
                {
                    **_db_user_to_record(db_user),
                    "shipping_rules": get_seller_shipping_rules(str(username)),
                }
            )
            if fresh_user != user:
                session[SESSION_USER_KEY] = fresh_user
                session.modified = True
            return fresh_user
        logout(session)
        return None
    current_record = local_store.get_user_by_username(str(username))
    if not current_record:
        return user
    if current_record.get("account_status", ACCOUNT_STATUS_ACTIVE) != ACCOUNT_STATUS_ACTIVE:
        logout(session)
        return None
    fresh_user = _user_snapshot(current_record)
    if fresh_user != user:
        session[SESSION_USER_KEY] = fresh_user
        session.modified = True
    return fresh_user


def require_user(session) -> Dict[str, Any]:
    # 需要登入的 API 一律走這個入口，沒有有效 session 就直接丟 PermissionError。
    """要求目前 session 必須已登入，否則拋出錯誤。"""
    user = get_current_user(session)
    if not user:
        raise PermissionError("Please log in first.")
    return user
