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
from django.utils import timezone

from ..repositories import local_store

SESSION_USER_KEY = "demo_user"
SELLER_REQUEST_PENDING = "pending"
SELLER_REQUEST_REJECTED = "rejected"
SELLER_REQUEST_APPROVED = "approved"
ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_SUSPENDED = "suspended"
ADMIN_ROLES = {"admin", "staff"}
SELLER_ROLES = {"seller", "admin", "staff"}


def _user_snapshot(user: Dict[str, Any]) -> Dict[str, Any]:
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
    }


def _is_hashed_password(value: str) -> bool:
    """判斷字串是否為 Django password hasher 產生的值。"""
    try:
        identify_hasher(value)
        return True
    except Exception:
        return False


def _save_user_patch(username: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新單一會員欄位並寫回 JSON。"""
    users = deepcopy(local_store.get_users())
    for item in users:
        if item.get("username") != username:
            continue
        item.update(patch)
        local_store.save_users(users)
        return local_store.get_user_by_username(username)
    return None


def _upgrade_legacy_password(user: Dict[str, Any], raw_password: str) -> None:
    """若舊資料仍保存明文密碼，首次登入時升級成 hash。"""
    users = deepcopy(local_store.get_users())
    for item in users:
        if item.get("username") != user["username"]:
            continue
        item["password_hash"] = make_password(raw_password)
        item.pop("password", None)
        item["updated_at"] = timezone.now().isoformat()
        local_store.save_users(users)
        return


def _mark_login(username: str) -> Optional[Dict[str, Any]]:
    """記錄最後登入時間，方便未來轉資料庫。"""
    now = timezone.now().isoformat()
    return _save_user_patch(username, {"last_login_at": now, "updated_at": now})


def is_admin(user: Dict[str, Any] | None) -> bool:
    """判斷目前會員是否具備管理員角色。"""
    return bool(user and user.get("role") in ADMIN_ROLES)


def is_seller(user: Dict[str, Any] | None) -> bool:
    """判斷目前會員是否具備賣家角色。"""
    return bool(user and user.get("role") in SELLER_ROLES)


def is_active(user: Dict[str, Any] | None) -> bool:
    """判斷目前會員是否為可使用中的帳號。"""
    return bool(user and user.get("account_status", ACCOUNT_STATUS_ACTIVE) == ACCOUNT_STATUS_ACTIVE)


def authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    """驗證會員帳密，成功時回傳 session 用使用者快照。"""
    clean_username = username.strip().lower()
    user = local_store.get_user_by_username(clean_username)
    if not user:
        return None
    if user.get("account_status", ACCOUNT_STATUS_ACTIVE) != ACCOUNT_STATUS_ACTIVE:
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
    if local_store.get_user_by_username(clean_username):
        raise ValueError("This username is already taken.")
    if not clean_display_name:
        raise ValueError("Display name is required.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    users = deepcopy(local_store.get_users())
    next_id = max([int(item.get("id", 0)) for item in users] or [0]) + 1
    now = timezone.now().isoformat()
    user = {
        "id": next_id,
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
    users.append(user)
    local_store.save_users(users)
    return _user_snapshot(user)


def update_profile(username: str, display_name: str, new_password: str = "", email: str = "") -> Dict[str, Any]:
    """更新會員顯示名稱、密碼與信箱。"""
    clean_display_name = display_name.strip()
    clean_email = email.strip().lower()
    if not clean_display_name:
        raise ValueError("Display name is required.")
    if new_password and len(new_password) < 6:
        raise ValueError("New password must be at least 6 characters.")

    users = deepcopy(local_store.get_users())
    for item in users:
        if item.get("username") != username:
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


def request_seller_role(username: str) -> Dict[str, Any]:
    """提出賣家資格申請。"""
    users = deepcopy(local_store.get_users())
    for item in users:
        if item.get("username") != username:
            continue
        if item.get("role") in SELLER_ROLES:
            raise ValueError("You already have seller access.")
        now = timezone.now().isoformat()
        item["seller_request_status"] = SELLER_REQUEST_PENDING
        item["seller_requested_at"] = now
        item["updated_at"] = now
        local_store.save_users(users)
        return _user_snapshot(item)
    raise ValueError("User not found.")


def list_seller_requests() -> list[Dict[str, Any]]:
    """列出待審核的賣家申請。"""
    requests = [user for user in local_store.get_users() if user.get("seller_request_status") == SELLER_REQUEST_PENDING]
    return sorted(requests, key=lambda item: item.get("seller_requested_at", ""), reverse=True)


def review_seller_request(username: str, approved: bool) -> Dict[str, Any]:
    """審核賣家申請。"""
    users = deepcopy(local_store.get_users())
    for item in users:
        if item.get("username") != username:
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
        return _user_snapshot(item)
    raise ValueError("User not found.")


def list_users(search: str = "", role: str = "", account_status: str = "") -> list[Dict[str, Any]]:
    """查詢會員清單。"""
    search_value = search.strip().lower()
    role_value = role.strip().lower()
    status_value = account_status.strip().lower()
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
    """更新會員帳號狀態。"""
    clean_status = account_status.strip().lower()
    if clean_status not in {ACCOUNT_STATUS_ACTIVE, ACCOUNT_STATUS_SUSPENDED}:
        raise ValueError("Invalid account status.")
    users = deepcopy(local_store.get_users())
    for item in users:
        if item.get("username") != username:
            continue
        now = timezone.now().isoformat()
        item["account_status"] = clean_status
        item["account_status_updated_at"] = now
        item["updated_at"] = now
        local_store.save_users(users)
        return _user_snapshot(item)
    raise ValueError("User not found.")


def login(session, user: Dict[str, Any]) -> None:
    """將會員快照寫入 session，並同步更新登入時間。"""
    refreshed = _mark_login(str(user["username"]))
    session[SESSION_USER_KEY] = _user_snapshot(refreshed or user)
    session.modified = True


def logout(session) -> None:
    """清除目前 session 的會員資訊。"""
    session.pop(SESSION_USER_KEY, None)
    session.modified = True


def get_current_user(session) -> Optional[Dict[str, Any]]:
    """從 session 取回目前登入會員，並與 JSON 最新資料同步。"""
    user = session.get(SESSION_USER_KEY)
    if not isinstance(user, dict):
        return None
    username = user.get("username")
    if not username:
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
    """要求目前 session 必須已登入，否則拋出錯誤。"""
    user = get_current_user(session)
    if not user:
        raise PermissionError("Please log in first.")
    return user
