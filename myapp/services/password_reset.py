"""Password-reset flow with a development mailbox."""

from __future__ import annotations

from datetime import datetime, timedelta
import secrets
from typing import Any, Dict, List
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from ..models import AppUser as AppUserModel
from ..models import PasswordResetToken as PasswordResetTokenModel
from . import auth_demo

TOKEN_TTL_MINUTES = 30
MAILBOX_LIMIT = 25
ADMIN_RECORD_LIMIT = 100
INVALID_TOKEN_MESSAGE = "Reset link is invalid or expired."


def _db_enabled() -> bool:
    try:
        AppUserModel.objects.count()
        PasswordResetTokenModel.objects.count()
        return True
    except Exception:
        return False


def _iso(value: Any) -> str:
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _parse_dt(value: Any):
    if not value:
        return None
    if hasattr(value, "tzinfo"):
        return value
    return datetime.fromisoformat(str(value))


def _frontend_origin() -> str:
    return str(getattr(settings, "FRONTEND_ORIGIN", "http://localhost:3000")).rstrip("/")


def _build_reset_url(token: str) -> str:
    return f"{_frontend_origin()}/reset-password?token={quote(token)}"


def _is_expired(expires_at) -> bool:
    return bool(expires_at and expires_at <= timezone.now())


def _db_record_to_dict(record: PasswordResetTokenModel) -> Dict[str, Any]:
    return {
        "id": record.id,
        "username": record.user.username,
        "display_name": record.user.display_name or record.user.username,
        "email": record.email,
        "token": record.token,
        "reset_url": _build_reset_url(record.token),
        "created_at": _iso(record.created_at),
        "expires_at": _iso(record.expires_at),
        "used_at": _iso(record.used_at),
    }


def _normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(record)
    normalized["username"] = str(normalized.get("username") or "").strip().lower()
    normalized["display_name"] = str(normalized.get("display_name") or normalized["username"])
    normalized["email"] = str(normalized.get("email") or "").strip().lower()
    normalized["token"] = str(normalized.get("token") or "")
    normalized["reset_url"] = str(normalized.get("reset_url") or _build_reset_url(normalized["token"]))
    normalized["created_at"] = str(normalized.get("created_at") or "")
    normalized["expires_at"] = str(normalized.get("expires_at") or "")
    normalized["used_at"] = str(normalized.get("used_at") or "")
    return normalized


def _mailbox_item(record: Dict[str, Any]) -> Dict[str, Any]:
    created_at = _parse_dt(record.get("created_at"))
    expires_at = _parse_dt(record.get("expires_at"))
    used_at = _parse_dt(record.get("used_at"))
    status = "used" if used_at else ("expired" if _is_expired(expires_at) else "active")
    return {
        **record,
        "is_used": bool(used_at),
        "is_expired": _is_expired(expires_at),
        "status": status,
        "status_label": {
            "active": "可使用",
            "used": "已使用",
            "expired": "已過期",
        }[status],
        "subject": "密碼重設連結",
        "preview": f"系統已為 {record.get('display_name') or record.get('username')} 準備密碼重設連結。",
        "created_at_display": created_at.strftime("%Y-%m-%d %H:%M") if created_at else "",
        "expires_at_display": expires_at.strftime("%Y-%m-%d %H:%M") if expires_at else "",
        "used_at_display": used_at.strftime("%Y-%m-%d %H:%M") if used_at else "",
    }


def _list_db_records() -> List[Dict[str, Any]]:
    queryset = PasswordResetTokenModel.objects.select_related("user").all().order_by("-created_at")
    return [_db_record_to_dict(item) for item in queryset]


def request_password_reset(email: str) -> Dict[str, Any]:
    clean_email = str(email or "").strip().lower()
    if not clean_email:
        raise ValueError("Email is required.")

    user = auth_demo.get_user_by_email(clean_email)
    if not user:
        return {"detail": "If the email exists, a reset link has been prepared in the dev mailbox.", "created": False}

    token = secrets.token_urlsafe(32)
    now = timezone.now()
    record = {
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
        "email": clean_email,
        "token": token,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=TOKEN_TTL_MINUTES)).isoformat(),
        "used_at": "",
        "reset_url": _build_reset_url(token),
    }

    db_user = AppUserModel.objects.get(username=user["username"])
    PasswordResetTokenModel.objects.create(
        user=db_user,
        email=clean_email,
        token=token,
        expires_at=now + timedelta(minutes=TOKEN_TTL_MINUTES),
    )

    return {"detail": "If the email exists, a reset link has been prepared in the dev mailbox.", "created": True}


def list_dev_mailbox(email: str = "") -> List[Dict[str, Any]]:
    clean_email = str(email or "").strip().lower()
    records = _list_db_records()
    if clean_email:
        records = [item for item in records if item.get("email") == clean_email]
    return [_mailbox_item(item) for item in records[:MAILBOX_LIMIT]]


def list_reset_records(email: str = "", status: str = "", limit: int = ADMIN_RECORD_LIMIT) -> List[Dict[str, Any]]:
    clean_status = str(status or "").strip().lower()
    items = list_dev_mailbox(email)
    if clean_status:
        items = [item for item in items if str(item.get("status") or "").strip().lower() == clean_status]
    return items[: max(1, int(limit or ADMIN_RECORD_LIMIT))]


def get_token_status(token: str) -> Dict[str, Any]:
    clean_token = str(token or "").strip()
    if not clean_token:
        raise ValueError(INVALID_TOKEN_MESSAGE)

    record = PasswordResetTokenModel.objects.select_related("user").filter(token=clean_token).first()
    if not record:
        raise ValueError(INVALID_TOKEN_MESSAGE)
    payload = _mailbox_item(_db_record_to_dict(record))

    if payload["is_used"] or payload["is_expired"]:
        raise ValueError(INVALID_TOKEN_MESSAGE)
    return payload


def _mark_token_used(token: str) -> None:
    used_at = timezone.now()
    PasswordResetTokenModel.objects.filter(token=token, used_at__isnull=True).update(used_at=used_at)


def confirm_password_reset(token: str, new_password: str) -> Dict[str, Any]:
    payload = get_token_status(token)
    user = auth_demo.set_password(payload["username"], new_password)
    _mark_token_used(token)
    return user
