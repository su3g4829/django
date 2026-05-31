from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from ..repositories import local_store

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
EXPECTED_IMAGE_WIDTH = 2240
EXPECTED_IMAGE_HEIGHT = 840

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

POSITION_HOME_MAIN = "home_main"

STATUS_LABELS = {
    STATUS_PENDING: "待審核",
    STATUS_APPROVED: "已通過",
    STATUS_REJECTED: "已拒絕",
}

POSITION_LABELS = {
    POSITION_HOME_MAIN: "首頁主 Banner",
}


def _upload_dir() -> Path:
    return Path(settings.BASE_DIR) / "static" / "uploads" / "banners"


def _iso_now() -> str:
    return timezone.localtime().isoformat()


def _parse_date(value: str) -> date | None:
    clean_value = str(value or "").strip()
    if not clean_value:
        return None
    try:
        return date.fromisoformat(clean_value[:10])
    except ValueError:
        return None


def _normalize_banner(item: Dict[str, Any]) -> Dict[str, Any]:
    position = str(item.get("position", POSITION_HOME_MAIN)).strip() or POSITION_HOME_MAIN
    status = str(item.get("status", STATUS_APPROVED if item.get("image_path") else STATUS_PENDING)).strip() or STATUS_PENDING
    starts_at = str(item.get("starts_at", "")).strip()
    ends_at = str(item.get("ends_at", "")).strip()

    normalized = {
        "id": int(item.get("id", 0)),
        "title": str(item.get("title", "")).strip(),
        "copy_text": str(item.get("copy_text", item.get("subtitle", ""))).strip(),
        "image_path": str(item.get("image_path", "")).strip(),
        "link_url": str(item.get("link_url", "")).strip(),
        "starts_at": starts_at,
        "ends_at": ends_at,
        "position": position,
        "position_label": POSITION_LABELS.get(position, position),
        "note": str(item.get("note", "")).strip(),
        "sort_order": max(1, int(item.get("sort_order", 1) or 1)),
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "is_active": bool(item.get("is_active", status == STATUS_APPROVED)),
        "rejection_reason": str(item.get("rejection_reason", "")).strip(),
        "applicant_user_id": item.get("applicant_user_id"),
        "applicant_username": str(item.get("applicant_username", "")).strip(),
        "applicant_display_name": str(item.get("applicant_display_name", "")).strip(),
        "reviewed_at": str(item.get("reviewed_at", "")).strip(),
        "reviewed_by_username": str(item.get("reviewed_by_username", "")).strip(),
        "reviewed_by_display_name": str(item.get("reviewed_by_display_name", "")).strip(),
        "created_at": str(item.get("created_at", "")).strip(),
        "updated_at": str(item.get("updated_at", "")).strip(),
    }
    normalized["is_currently_visible"] = _is_banner_visible(normalized)
    return normalized


def _sort_banners(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted((_normalize_banner(item) for item in items), key=lambda item: (item["sort_order"], item["id"]))


def _sort_user_applications(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = [_normalize_banner(item) for item in items]
    return sorted(normalized, key=lambda item: (item["updated_at"], item["created_at"], item["id"]), reverse=True)


def _validate_schedule(starts_at: str, ends_at: str) -> tuple[str, str]:
    start_date = _parse_date(starts_at)
    end_date = _parse_date(ends_at)
    if not start_date or not end_date:
        raise ValueError("Please provide valid start and end dates.")
    if end_date < start_date:
        raise ValueError("End date must be on or after the start date.")
    return (start_date.isoformat(), end_date.isoformat())


def _validate_position(position: str) -> str:
    clean_position = str(position or "").strip() or POSITION_HOME_MAIN
    if clean_position not in POSITION_LABELS:
        raise ValueError("Unsupported banner placement.")
    return clean_position


def _save_uploaded_image(uploaded_file: UploadedFile) -> str:
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Only jpg, jpeg, png, and webp images are allowed.")
    if uploaded_file.size > MAX_IMAGE_SIZE_BYTES:
        raise ValueError("Each image must be 5 MB or smaller.")

    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    file_name = f"banner-{timestamp}{extension}"
    target_path = upload_dir / file_name
    with target_path.open("wb") as output:
        for chunk in uploaded_file.chunks():
            output.write(chunk)
    return f"/static/uploads/banners/{file_name}"


def _delete_uploaded_image(image_path: str) -> None:
    if not image_path.startswith("/static/uploads/banners/"):
        return
    relative = image_path.lstrip("/").replace("/", "\\")
    target = Path(settings.BASE_DIR) / relative
    if target.exists():
        target.unlink()


def _is_banner_visible(item: Dict[str, Any]) -> bool:
    if item.get("status") != STATUS_APPROVED:
        return False
    if not item.get("is_active") or not item.get("image_path"):
        return False

    today = timezone.localdate()
    starts_at = _parse_date(str(item.get("starts_at", "")))
    ends_at = _parse_date(str(item.get("ends_at", "")))
    if not starts_at or not ends_at:
        return False
    return starts_at <= today <= ends_at


def _next_id(items: List[Dict[str, Any]]) -> int:
    return max((item["id"] for item in items), default=0) + 1


def _next_sort_order(items: List[Dict[str, Any]]) -> int:
    approved_items = [item for item in items if item.get("status") == STATUS_APPROVED]
    return max((item["sort_order"] for item in approved_items), default=0) + 1


def _find_banner(banner_id: int) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    banners = [_normalize_banner(item) for item in local_store.get_banners()]
    for banner in banners:
        if banner["id"] == banner_id:
            return banners, banner
    raise ValueError("Banner not found.")


def list_public_banners() -> List[Dict[str, Any]]:
    return [item for item in _sort_banners(local_store.get_banners()) if item.get("is_currently_visible")]


def list_user_applications(username: str) -> List[Dict[str, Any]]:
    clean_username = str(username or "").strip().lower()
    return _sort_user_applications(
        item for item in local_store.get_banners() if str(item.get("applicant_username", "")).strip().lower() == clean_username
    )


def list_admin_banners() -> List[Dict[str, Any]]:
    return _sort_user_applications(local_store.get_banners())


def submit_banner_application(
    *,
    user: Dict[str, Any],
    title: str,
    copy_text: str,
    link_url: str,
    starts_at: str,
    ends_at: str,
    position: str,
    note: str,
    uploaded_image: UploadedFile,
) -> Dict[str, Any]:
    if not uploaded_image:
        raise ValueError("Please upload a banner image.")

    validated_starts_at, validated_ends_at = _validate_schedule(starts_at, ends_at)
    validated_position = _validate_position(position)
    banners = [_normalize_banner(item) for item in local_store.get_banners()]
    now = _iso_now()
    record = {
        "id": _next_id(banners),
        "title": str(title).strip(),
        "copy_text": str(copy_text).strip(),
        "image_path": _save_uploaded_image(uploaded_image),
        "link_url": str(link_url).strip(),
        "starts_at": validated_starts_at,
        "ends_at": validated_ends_at,
        "position": validated_position,
        "note": str(note).strip(),
        "sort_order": _next_sort_order(banners),
        "status": STATUS_PENDING,
        "is_active": False,
        "rejection_reason": "",
        "applicant_user_id": user.get("id"),
        "applicant_username": str(user.get("username", "")).strip(),
        "applicant_display_name": str(user.get("display_name", "")).strip(),
        "reviewed_at": "",
        "reviewed_by_username": "",
        "reviewed_by_display_name": "",
        "created_at": now,
        "updated_at": now,
    }
    banners.append(record)
    local_store.save_banners(banners)
    return _normalize_banner(record)


def create_admin_banner(
    *,
    user: Dict[str, Any],
    title: str,
    copy_text: str,
    link_url: str,
    starts_at: str,
    ends_at: str,
    position: str,
    note: str,
    is_active: bool,
    uploaded_image: UploadedFile,
) -> Dict[str, Any]:
    if not uploaded_image:
        raise ValueError("Please upload a banner image.")

    validated_starts_at, validated_ends_at = _validate_schedule(starts_at, ends_at)
    validated_position = _validate_position(position)
    banners = [_normalize_banner(item) for item in local_store.get_banners()]
    now = _iso_now()
    record = {
        "id": _next_id(banners),
        "title": str(title).strip(),
        "copy_text": str(copy_text).strip(),
        "image_path": _save_uploaded_image(uploaded_image),
        "link_url": str(link_url).strip(),
        "starts_at": validated_starts_at,
        "ends_at": validated_ends_at,
        "position": validated_position,
        "note": str(note).strip(),
        "sort_order": _next_sort_order(banners),
        "status": STATUS_APPROVED,
        "is_active": bool(is_active),
        "rejection_reason": "",
        "applicant_user_id": user.get("id"),
        "applicant_username": str(user.get("username", "")).strip(),
        "applicant_display_name": str(user.get("display_name", "")).strip(),
        "reviewed_at": now,
        "reviewed_by_username": str(user.get("username", "")).strip(),
        "reviewed_by_display_name": str(user.get("display_name", "")).strip(),
        "created_at": now,
        "updated_at": now,
    }
    banners.append(record)
    local_store.save_banners(banners)
    return _normalize_banner(record)


def update_banner(
    *,
    banner_id: int,
    title: str,
    copy_text: str,
    link_url: str,
    starts_at: str,
    ends_at: str,
    position: str,
    note: str,
    is_active: bool,
    sort_order: int,
    uploaded_image: UploadedFile | None = None,
) -> Dict[str, Any]:
    banners, banner = _find_banner(banner_id)
    validated_starts_at, validated_ends_at = _validate_schedule(starts_at, ends_at)
    validated_position = _validate_position(position)

    if uploaded_image:
        _delete_uploaded_image(banner.get("image_path", ""))
        banner["image_path"] = _save_uploaded_image(uploaded_image)

    banner["title"] = str(title).strip()
    banner["copy_text"] = str(copy_text).strip()
    banner["link_url"] = str(link_url).strip()
    banner["starts_at"] = validated_starts_at
    banner["ends_at"] = validated_ends_at
    banner["position"] = validated_position
    banner["note"] = str(note).strip()
    banner["is_active"] = bool(is_active)
    banner["sort_order"] = max(1, int(sort_order or 1))
    banner["updated_at"] = _iso_now()
    local_store.save_banners(banners)
    return _normalize_banner(banner)


def review_banner_application(
    *,
    banner_id: int,
    reviewer: Dict[str, Any],
    approved: bool,
    rejection_reason: str = "",
) -> Dict[str, Any]:
    banners, banner = _find_banner(banner_id)
    banner["status"] = STATUS_APPROVED if approved else STATUS_REJECTED
    banner["status_label"] = STATUS_LABELS[banner["status"]]
    banner["is_active"] = bool(approved)
    banner["rejection_reason"] = "" if approved else str(rejection_reason).strip()
    banner["reviewed_at"] = _iso_now()
    banner["reviewed_by_username"] = str(reviewer.get("username", "")).strip()
    banner["reviewed_by_display_name"] = str(reviewer.get("display_name", "")).strip()
    banner["updated_at"] = banner["reviewed_at"]
    if not approved and not banner["rejection_reason"]:
        raise ValueError("Please provide a rejection reason.")
    local_store.save_banners(banners)
    return _normalize_banner(banner)


def delete_banner(banner_id: int) -> None:
    banners = [_normalize_banner(item) for item in local_store.get_banners()]
    for index, banner in enumerate(banners):
        if banner["id"] != banner_id:
            continue
        _delete_uploaded_image(banner.get("image_path", ""))
        del banners[index]
        approved_items = [item for item in _sort_banners(banners) if item.get("status") == STATUS_APPROVED]
        for order_index, item in enumerate(approved_items, start=1):
            item["sort_order"] = order_index
        local_store.save_banners(banners)
        return
    raise ValueError("Banner not found.")


def reorder_banners(ids: List[int]) -> List[Dict[str, Any]]:
    banners = [_normalize_banner(item) for item in local_store.get_banners()]
    approved_items = [item for item in banners if item.get("status") == STATUS_APPROVED]
    banner_map = {item["id"]: item for item in approved_items}
    ordered_ids = [banner_id for banner_id in ids if banner_id in banner_map]
    remaining_ids = [item["id"] for item in _sort_banners(approved_items) if item["id"] not in ordered_ids]
    final_ids = ordered_ids + remaining_ids

    for index, banner_id in enumerate(final_ids, start=1):
        banner_map[banner_id]["sort_order"] = index
        banner_map[banner_id]["updated_at"] = _iso_now()

    local_store.save_banners(banners)
    return list_admin_banners()
