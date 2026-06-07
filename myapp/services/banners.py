from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import connection
from django.utils import timezone

from ..models import AppUser as AppUserModel
from ..models import Banner as BannerModel
from ..models import MediaAsset as MediaAssetModel
from ..repositories import local_store
from . import cloud_storage as cloud_storage_service

# Banner service 負責前台輪播、會員申請投放與後台審核管理。
# 資料在 ORM 可用時優先走資料庫，否則退回 local JSON snapshot。

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
LOCAL_LINK_HOSTS = {"localhost", "127.0.0.1"}


def _upload_dir() -> Path:
    # Banner 圖片統一存放在 static/uploads/banners，避免和商品圖混用。
    return Path(settings.BASE_DIR) / "static" / "uploads" / "banners"


def _iso_now() -> str:
    # Banner 寫入流程一律用本地時區 ISO 字串當時間欄位。
    return timezone.localtime().isoformat()


def _parse_date(value: Any) -> date | None:
    # 檔期只需要日期，不需要時間；這裡把輸入寬鬆轉成 `date`。
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    clean_value = str(value or "").strip()
    if not clean_value:
        return None
    try:
        return date.fromisoformat(clean_value[:10])
    except ValueError:
        return None


def _start_of_day(value: date) -> datetime:
    # Banner 排程寫 ORM 時，開始日固定落在當天 00:00。
    return timezone.make_aware(datetime.combine(value, time.min), timezone.get_current_timezone())


def _end_of_day(value: date) -> datetime:
    # Banner 排程寫 ORM 時，結束日固定落在當天 23:59:59。
    return timezone.make_aware(datetime.combine(value, time.max), timezone.get_current_timezone())


def _date_string(value: datetime | None) -> str:
    # ORM datetime 欄位回前端時，只保留 date 部分給 Banner 表單使用。
    if not value:
        return ""
    return timezone.localtime(value).date().isoformat()


def _datetime_string(value: datetime | None) -> str:
    # reviewed_at / updated_at 等欄位維持完整 ISO datetime 給管理端顯示。
    if not value:
        return ""
    return timezone.localtime(value).isoformat()


def _db_banners_enabled() -> bool:
    # Banner 表存在且可查詢時，投放與審核流程就優先走 ORM。
    try:
        tables = set(connection.introspection.table_names())
    except Exception:
        return False
    return BannerModel._meta.db_table in tables


def _legacy_username(user: AppUserModel | None) -> str:
    # Banner payload 內的 username 一律標準化成小寫字串。
    if not user:
        return ""
    return str(user.username or "").strip().lower()


def _db_user_from_payload(
    *,
    username: str = "",
    display_name: str = "",
    role: str = "member",
    user_id: int | None = None,
) -> AppUserModel | None:
    # 申請人 / 審核人若要寫進 ORM Banner，需要先解析成對應的 `AppUser`。
    if not _db_banners_enabled():
        return None
    if user_id:
        try:
            existing = AppUserModel.objects.filter(id=user_id).first()
        except Exception:
            return None
        if existing:
            return existing
    clean_username = str(username or "").strip().lower()
    if not clean_username:
        return None
    defaults = {
        "email": f"{clean_username}@example.com",
        "display_name": str(display_name or clean_username).strip() or clean_username,
        "role": role or "member",
    }
    try:
        user, _ = AppUserModel.objects.get_or_create(username=clean_username, defaults=defaults)
    except Exception:
        return None
    return user


def _normalize_link_url(link_url: Any) -> str:
    raw = str(link_url or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if not parsed.scheme and not parsed.netloc:
        return raw
    if parsed.hostname and parsed.hostname.lower() in LOCAL_LINK_HOSTS:
        relative = parsed.path or "/"
        if parsed.query:
            relative = f"{relative}?{parsed.query}"
        if parsed.fragment:
            relative = f"{relative}#{parsed.fragment}"
        return relative
    return raw


def _replace_product_slug_in_link(link_url: str, old_slug: str, new_slug: str) -> str:
    normalized = _normalize_link_url(link_url)
    clean_old_slug = str(old_slug or "").strip()
    clean_new_slug = str(new_slug or "").strip()
    if not normalized or not clean_old_slug or not clean_new_slug or clean_old_slug == clean_new_slug:
        return normalized
    parsed = urlsplit(normalized)
    path = parsed.path or normalized
    if path not in {f"/products/{clean_old_slug}", f"/products/{clean_old_slug}/"}:
        return normalized
    next_path = f"/products/{clean_new_slug}"
    if path.endswith("/"):
        next_path = f"{next_path}/"
    if not parsed.scheme and not parsed.netloc:
        rewritten = next_path
        if parsed.query:
            rewritten = f"{rewritten}?{parsed.query}"
        if parsed.fragment:
            rewritten = f"{rewritten}#{parsed.fragment}"
        return rewritten
    return urlunsplit((parsed.scheme, parsed.netloc, next_path, parsed.query, parsed.fragment))


def _normalize_banner(item: Dict[str, Any]) -> Dict[str, Any]:
    # 不論資料來自 ORM 或 JSON，都先整理成同一份 Banner payload，方便前台與後台共用。
    position = str(item.get("position", POSITION_HOME_MAIN)).strip() or POSITION_HOME_MAIN
    status = str(item.get("status", STATUS_APPROVED if item.get("image_path") else STATUS_PENDING)).strip() or STATUS_PENDING
    starts_at = str(item.get("starts_at", "")).strip()
    ends_at = str(item.get("ends_at", "")).strip()

    normalized = {
        "id": int(item.get("id", 0)),
        "title": str(item.get("title", "")).strip(),
        "copy_text": str(item.get("copy_text", item.get("subtitle", ""))).strip(),
        "image_path": str(item.get("image_path", "")).strip(),
        "link_url": _normalize_link_url(item.get("link_url", "")),
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


def _db_banner_to_record(banner: BannerModel) -> Dict[str, Any]:
    # ORM Banner row 轉成前端 / 後台管理都可直接使用的 dict 結構。
    reviewed_at = _datetime_string(banner.updated_at) if banner.reviewed_by_id or banner.status != STATUS_PENDING else ""
    record = {
        "id": banner.id,
        "title": str(banner.title or "").strip(),
        "copy_text": str(banner.copy_text or "").strip(),
        "image_path": str(banner.image_path or "").strip(),
        "link_url": str(banner.link_url or "").strip(),
        "starts_at": _date_string(banner.starts_at),
        "ends_at": _date_string(banner.ends_at),
        "position": str(banner.position or POSITION_HOME_MAIN).strip() or POSITION_HOME_MAIN,
        "note": str(banner.note or "").strip(),
        "sort_order": max(1, int(banner.sort_order or 1)),
        "status": str(banner.status or STATUS_PENDING).strip() or STATUS_PENDING,
        "is_active": bool(banner.is_active),
        "rejection_reason": str(banner.rejection_reason or "").strip(),
        "applicant_user_id": banner.applicant_user_id,
        "applicant_username": _legacy_username(banner.applicant_user),
        "applicant_display_name": str(getattr(banner.applicant_user, "display_name", "") or "").strip(),
        "reviewed_at": reviewed_at,
        "reviewed_by_username": _legacy_username(banner.reviewed_by),
        "reviewed_by_display_name": str(getattr(banner.reviewed_by, "display_name", "") or "").strip(),
        "created_at": _datetime_string(banner.created_at),
        "updated_at": _datetime_string(banner.updated_at),
    }
    return _normalize_banner(record)


def _sort_banners(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # 前台顯示順序以 sort_order 為主，再用 id 做穩定排序。
    return sorted((_normalize_banner(item) for item in items), key=lambda item: (item["sort_order"], item["id"]))


def _sort_user_applications(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # 會員申請列表與後台列表偏重最近更新，因此按 updated_at 倒序。
    normalized = [_normalize_banner(item) for item in items]
    return sorted(normalized, key=lambda item: (item["updated_at"], item["created_at"], item["id"]), reverse=True)


def _validate_schedule(starts_at: Any, ends_at: Any) -> tuple[str, str]:
    # Banner 檔期至少要有合法開始 / 結束日期，且結束日不能早於開始日。
    start_date = _parse_date(starts_at)
    end_date = _parse_date(ends_at)
    if not start_date or not end_date:
        raise ValueError("Please provide valid start and end dates.")
    if end_date < start_date:
        raise ValueError("End date must be on or after the start date.")
    return (start_date.isoformat(), end_date.isoformat())


def _validate_position(position: str) -> str:
    # 目前 Banner 版位是白名單式控制，避免寫入不存在的 placement。
    clean_position = str(position or "").strip() or POSITION_HOME_MAIN
    if clean_position not in POSITION_LABELS:
        raise ValueError("Unsupported banner placement.")
    return clean_position


def _save_uploaded_image(uploaded_file: UploadedFile) -> str:
    # Banner 圖片上傳統一在這裡驗證副檔名與大小，再存成本地靜態檔。
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Only jpg, jpeg, png, and webp images are allowed.")
    if uploaded_file.size > MAX_IMAGE_SIZE_BYTES:
        raise ValueError("Each image must be 5 MB or smaller.")

    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    file_name = f"banner-{timestamp}{extension}"
    object_name = f"banners/{file_name}"
    if cloud_storage_service.is_enabled():
        uploaded_path = cloud_storage_service.upload_image(uploaded_file, object_name)
        if not uploaded_path:
            raise ValueError("Unable to upload the image to cloud storage.")
        return uploaded_path
    target_path = upload_dir / file_name
    with target_path.open("wb") as output:
        for chunk in uploaded_file.chunks():
            output.write(chunk)
    return f"/static/uploads/banners/{file_name}"


def _delete_uploaded_image(image_path: str) -> None:
    # 刪除 Banner 時除了本機圖片，也同步清掉對應的 media asset 紀錄。
    if cloud_storage_service.delete_by_public_url(image_path):
        if _db_banners_enabled():
            MediaAssetModel.objects.filter(file_path=image_path).delete()
        return
    if not image_path.startswith("/static/uploads/banners/"):
        return
    relative = image_path.lstrip("/").replace("/", "\\")
    target = Path(settings.BASE_DIR) / relative
    if target.exists():
        target.unlink()
    if _db_banners_enabled():
        MediaAssetModel.objects.filter(file_path=image_path).delete()


def _save_media_asset(uploaded_file: UploadedFile, image_path: str, uploaded_by: AppUserModel | None) -> None:
    # ORM 模式下，Banner 上傳的圖片也會記錄到 media asset 方便後續追蹤。
    if not _db_banners_enabled():
        return
    MediaAssetModel.objects.create(
        uploaded_by=uploaded_by,
        file_path=image_path,
        file_name=Path(image_path).name,
        mime_type=str(uploaded_file.content_type or ""),
        file_size=int(uploaded_file.size or 0),
    )


def _is_banner_visible(item: Dict[str, Any]) -> bool:
    # 前台只顯示已核准、啟用中、且檔期包含今天的 Banner。
    if item.get("status") != STATUS_APPROVED:
        return False
    if not item.get("is_active") or not item.get("image_path"):
        return False

    today = timezone.localdate()
    starts_at = _parse_date(item.get("starts_at", ""))
    ends_at = _parse_date(item.get("ends_at", ""))
    if not starts_at or not ends_at:
        return False
    return starts_at <= today <= ends_at


def _persist_banner_record(record: Dict[str, Any]) -> None:
    # JSON fallback 模式下，單筆 Banner 寫回 local snapshot。
    if _db_banners_enabled():
        return
    banners = [_normalize_banner(item) for item in local_store.get_banners()]
    target_id = int(record["id"])
    for index, item in enumerate(banners):
        if int(item.get("id", 0)) == target_id:
            banners[index] = _normalize_banner(record)
            break
    else:
        banners.append(_normalize_banner(record))
    local_store.save_banners(_sort_user_applications(banners))


def _persist_banners_snapshot(records: List[Dict[str, Any]]) -> None:
    # 需要整批重排 sort_order 時，集中從這裡覆蓋 JSON 快照。
    if _db_banners_enabled():
        return
    local_store.save_banners(_sort_user_applications(records))


def _sync_banner_record_to_orm(record: Dict[str, Any]) -> BannerModel:
    # Banner ORM 寫入主流程：主表欄位、申請人 / 審核人與檔期都在這裡同步。
    start_date = _parse_date(record.get("starts_at"))
    end_date = _parse_date(record.get("ends_at"))
    applicant = _db_user_from_payload(
        user_id=record.get("applicant_user_id"),
        username=str(record.get("applicant_username", "")),
        display_name=str(record.get("applicant_display_name", "")),
        role="member",
    )
    reviewer = _db_user_from_payload(
        username=str(record.get("reviewed_by_username", "")),
        display_name=str(record.get("reviewed_by_display_name", "")),
        role="admin",
    )
    banner, created = BannerModel.objects.update_or_create(
        id=int(record["id"]),
        defaults={
            "title": str(record.get("title", "")).strip(),
            "copy_text": str(record.get("copy_text", "")).strip(),
            "image_path": str(record.get("image_path", "")).strip(),
            "link_url": str(record.get("link_url", "")).strip(),
            "position": str(record.get("position", POSITION_HOME_MAIN)).strip() or POSITION_HOME_MAIN,
            "note": str(record.get("note", "")).strip(),
            "sort_order": max(1, int(record.get("sort_order", 1) or 1)),
            "status": str(record.get("status", STATUS_PENDING)).strip() or STATUS_PENDING,
            "rejection_reason": str(record.get("rejection_reason", "")).strip(),
            "applicant_user": applicant,
            "reviewed_by": reviewer,
            "starts_at": _start_of_day(start_date) if start_date else None,
            "ends_at": _end_of_day(end_date) if end_date else None,
            "is_active": bool(record.get("is_active")),
        },
    )
    created_at = record.get("created_at")
    updated_at = record.get("updated_at")
    update_kwargs: Dict[str, Any] = {}
    if created_at:
        try:
            update_kwargs["created_at"] = datetime.fromisoformat(str(created_at))
        except ValueError:
            pass
    if updated_at:
        try:
            update_kwargs["updated_at"] = datetime.fromisoformat(str(updated_at))
        except ValueError:
            pass
    if update_kwargs:
        BannerModel.objects.filter(pk=banner.pk).update(**update_kwargs)
        banner.refresh_from_db()
    elif created:
        banner.refresh_from_db()
    return banner


def _list_db_banners() -> List[Dict[str, Any]]:
    # 後台與前台若走 ORM，都先從這裡拿到標準化後的 Banner 清單。
    if not _db_banners_enabled():
        return []
    return [_db_banner_to_record(item) for item in BannerModel.objects.select_related("applicant_user", "reviewed_by").all()]


def _find_banner(banner_id: int) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    # 後台編輯 / 審核 / 刪除 Banner 前，先透過這個 helper 找到目標與當前列表。
    if _db_banners_enabled():
        banners = _list_db_banners()
    else:
        banners = [_normalize_banner(item) for item in local_store.get_banners()]
    for banner in banners:
        if banner["id"] == banner_id:
            return banners, banner
    raise ValueError("Banner not found.")


def list_public_banners() -> List[Dict[str, Any]]:
    # 前台首頁輪播只取目前可見的 Banner。
    if _db_banners_enabled():
        banners = _list_db_banners()
        return [item for item in _sort_banners(banners) if item.get("is_currently_visible")]
    return [item for item in _sort_banners(local_store.get_banners()) if item.get("is_currently_visible")]


def list_user_applications(username: str) -> List[Dict[str, Any]]:
    # 會員中心只顯示某位使用者自己提交的 Banner 申請。
    clean_username = str(username or "").strip().lower()
    if _db_banners_enabled():
        banners = _list_db_banners()
        return _sort_user_applications(
            item for item in banners if str(item.get("applicant_username", "")).strip().lower() == clean_username
        )
    return _sort_user_applications(
        item for item in local_store.get_banners() if str(item.get("applicant_username", "")).strip().lower() == clean_username
    )


def list_admin_banners() -> List[Dict[str, Any]]:
    # 後台需要看到所有 Banner，不論狀態是否可見。
    if _db_banners_enabled():
        banners = _list_db_banners()
        return _sort_user_applications(banners)
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
    # 一般會員提交 Banner 申請時，初始狀態一律是 pending，等待後台審核。
    if not uploaded_image:
        raise ValueError("Please upload a banner image.")

    validated_starts_at, validated_ends_at = _validate_schedule(starts_at, ends_at)
    validated_position = _validate_position(position)
    banners = list_admin_banners()
    now = _iso_now()
    record = {
        "id": max((item["id"] for item in banners), default=0) + 1,
        "title": str(title).strip(),
        "copy_text": str(copy_text).strip(),
        "image_path": _save_uploaded_image(uploaded_image),
        "link_url": _normalize_link_url(link_url),
        "starts_at": validated_starts_at,
        "ends_at": validated_ends_at,
        "position": validated_position,
        "note": str(note).strip(),
        "sort_order": max((item["sort_order"] for item in banners if item.get("status") == STATUS_APPROVED), default=0) + 1,
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
    db_user = None
    banner = None
    if _db_banners_enabled():
        db_user = _db_user_from_payload(
            user_id=user.get("id"),
            username=str(user.get("username", "")),
            display_name=str(user.get("display_name", "")),
            role=str(user.get("role", "member") or "member"),
        )
        banner = _sync_banner_record_to_orm(record)
    _persist_banner_record(_db_banner_to_record(banner) if banner else record)
    _save_media_asset(uploaded_image, record["image_path"], db_user)
    return _normalize_banner(_db_banner_to_record(banner) if banner else record)


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
    # 管理端可直接建立已核准 Banner，略過申請等待流程。
    if not uploaded_image:
        raise ValueError("Please upload a banner image.")

    validated_starts_at, validated_ends_at = _validate_schedule(starts_at, ends_at)
    validated_position = _validate_position(position)
    banners = list_admin_banners()
    now = _iso_now()
    record = {
        "id": max((item["id"] for item in banners), default=0) + 1,
        "title": str(title).strip(),
        "copy_text": str(copy_text).strip(),
        "image_path": _save_uploaded_image(uploaded_image),
        "link_url": _normalize_link_url(link_url),
        "starts_at": validated_starts_at,
        "ends_at": validated_ends_at,
        "position": validated_position,
        "note": str(note).strip(),
        "sort_order": max((item["sort_order"] for item in banners if item.get("status") == STATUS_APPROVED), default=0) + 1,
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
    db_user = None
    banner = None
    if _db_banners_enabled():
        db_user = _db_user_from_payload(
            user_id=user.get("id"),
            username=str(user.get("username", "")),
            display_name=str(user.get("display_name", "")),
            role=str(user.get("role", "admin") or "admin"),
        )
        banner = _sync_banner_record_to_orm(record)
    _persist_banner_record(_db_banner_to_record(banner) if banner else record)
    _save_media_asset(uploaded_image, record["image_path"], db_user)
    return _normalize_banner(_db_banner_to_record(banner) if banner else record)


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
    # 後台編輯 Banner 時可換圖、改檔期、調排序與啟用狀態。
    banners, banner = _find_banner(banner_id)
    validated_starts_at, validated_ends_at = _validate_schedule(starts_at, ends_at)
    validated_position = _validate_position(position)

    if uploaded_image:
        _delete_uploaded_image(banner.get("image_path", ""))
        banner["image_path"] = _save_uploaded_image(uploaded_image)
        _save_media_asset(uploaded_image, banner["image_path"], None)

    banner["title"] = str(title).strip()
    banner["copy_text"] = str(copy_text).strip()
    banner["link_url"] = _normalize_link_url(link_url)
    banner["starts_at"] = validated_starts_at
    banner["ends_at"] = validated_ends_at
    banner["position"] = validated_position
    banner["note"] = str(note).strip()
    banner["is_active"] = bool(is_active)
    banner["sort_order"] = max(1, int(sort_order or 1))
    banner["updated_at"] = _iso_now()
    if _db_banners_enabled():
        banner = _db_banner_to_record(_sync_banner_record_to_orm(banner))
    _persist_banner_record(banner)
    return _normalize_banner(banner)


def review_banner_application(
    *,
    banner_id: int,
    reviewer: Dict[str, Any],
    approved: bool,
    rejection_reason: str = "",
) -> Dict[str, Any]:
    # 審核申請時會切換狀態、記錄審核人與審核時間，駁回時必填原因。
    _, banner = _find_banner(banner_id)
    banner["status"] = STATUS_APPROVED if approved else STATUS_REJECTED
    banner["status_label"] = STATUS_LABELS[banner["status"]]
    banner["is_active"] = bool(approved)
    banner["rejection_reason"] = "" if approved else str(rejection_reason).strip()
    if not approved and not banner["rejection_reason"]:
        raise ValueError("Please provide a rejection reason.")
    banner["reviewed_at"] = _iso_now()
    banner["reviewed_by_username"] = str(reviewer.get("username", "")).strip()
    banner["reviewed_by_display_name"] = str(reviewer.get("display_name", "")).strip()
    banner["updated_at"] = banner["reviewed_at"]
    if _db_banners_enabled():
        banner = _db_banner_to_record(_sync_banner_record_to_orm(banner))
    _persist_banner_record(banner)
    return _normalize_banner(banner)


def delete_banner(banner_id: int) -> None:
    # 刪除 Banner 後，已核准 Banner 的 sort_order 會重新壓緊，避免前台排序出現空洞。
    banners = list_admin_banners()
    for index, banner in enumerate(banners):
        if banner["id"] != banner_id:
            continue
        _delete_uploaded_image(banner.get("image_path", ""))
        if _db_banners_enabled():
            BannerModel.objects.filter(id=banner_id).delete()
        del banners[index]
        approved_items = [item for item in _sort_banners(banners) if item.get("status") == STATUS_APPROVED]
        for order_index, item in enumerate(approved_items, start=1):
            item["sort_order"] = order_index
            if _db_banners_enabled():
                _sync_banner_record_to_orm(item)
        _persist_banners_snapshot(banners)
        return
    raise ValueError("Banner not found.")


def reorder_banners(ids: List[int]) -> List[Dict[str, Any]]:
    # 後台拖曳排序只影響已核准 Banner，未核准申請不參與前台排序。
    banners = list_admin_banners()
    approved_items = [item for item in banners if item.get("status") == STATUS_APPROVED]
    banner_map = {item["id"]: item for item in approved_items}
    ordered_ids = [banner_id for banner_id in ids if banner_id in banner_map]
    remaining_ids = [item["id"] for item in _sort_banners(approved_items) if item["id"] not in ordered_ids]
    final_ids = ordered_ids + remaining_ids

    now = _iso_now()
    for index, banner_id in enumerate(final_ids, start=1):
        banner_map[banner_id]["sort_order"] = index
        banner_map[banner_id]["updated_at"] = now
        if _db_banners_enabled():
            banner_map[banner_id] = _db_banner_to_record(_sync_banner_record_to_orm(banner_map[banner_id]))

    _persist_banners_snapshot(banners)
    return list_admin_banners()


def update_product_banner_links(old_slug: str, new_slug: str) -> int:
    clean_old_slug = str(old_slug or "").strip()
    clean_new_slug = str(new_slug or "").strip()
    if not clean_old_slug or not clean_new_slug or clean_old_slug == clean_new_slug:
        return 0

    banners = list_admin_banners()
    updated_count = 0
    now = _iso_now()
    for banner in banners:
        rewritten_link = _replace_product_slug_in_link(str(banner.get("link_url", "")), clean_old_slug, clean_new_slug)
        if rewritten_link == str(banner.get("link_url", "")):
            continue
        banner["link_url"] = rewritten_link
        banner["updated_at"] = now
        if _db_banners_enabled():
            _sync_banner_record_to_orm(banner)
        updated_count += 1

    if updated_count:
        _persist_banners_snapshot(banners)
    return updated_count
