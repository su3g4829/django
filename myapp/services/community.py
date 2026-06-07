"""社群論壇 service，採 ORM 優先並保留 JSON fallback。

這層負責整理貼文、回覆、投票與編輯器圖片上傳邏輯，讓社群頁、
貼文詳情頁與後台管理能共用一致的 payload。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import OperationalError, ProgrammingError
from django.test.testcases import DatabaseOperationForbidden
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..models import AppUser as AppUserModel
from ..models import CommunityPost as CommunityPostModel
from ..models import CommunityReply as CommunityReplyModel
from ..models import CommunityVote as CommunityVoteModel
from ..repositories import local_store
from . import cloud_storage as cloud_storage_service
from .privacy import anonymize_public_name

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_LEGACY_FALLBACK_EXCEPTIONS = (DatabaseOperationForbidden, OperationalError, ProgrammingError)


def _format_created_at(value: str) -> str:
    # 前台社群列表只需要固定的本地時間字串，這裡統一處理舊 ISO timestamp。
    parsed = parse_datetime(value) if value else None
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M") if parsed else ""


def _resolve_author_user_id(author_user_id: int | None, author_username: str | None) -> int | None:
    # 有些舊貼文只存 username，API 回傳前先補一個穩定的 author_user_id 方便前端判斷本人操作。
    if author_user_id:
        return int(author_user_id)
    if not author_username:
        return None
    clean_username = str(author_username).strip().lower()
    if not clean_username:
        return None
    try:
        user_id = AppUserModel.objects.filter(username=clean_username).values_list("id", flat=True).first()
        return int(user_id) if user_id else None
    except _LEGACY_FALLBACK_EXCEPTIONS:
        legacy_user = local_store.get_user_by_username(clean_username)
        if not legacy_user:
            return None
        legacy_id = legacy_user.get("id")
        return int(legacy_id) if legacy_id else None


def _community_upload_dir() -> Path:
    # 編輯器上傳圖片統一落在 static/uploads/community，避免和商品圖混在一起。
    return Path(settings.BASE_DIR) / "static" / "uploads" / "community"


def _legacy_username(user: AppUserModel) -> str:
    # 社群 payload 一律輸出標準化後的 username，降低 ORM / JSON 來源差異。
    return str(user.username or "").strip().lower()


def _get_or_create_author(author_username: str | None, author: str) -> AppUserModel:
    # 社群作者若尚未存在 ORM，就用最小欄位建立可關聯的 `AppUser`，不再回頭依賴 JSON 使用者資料。
    clean_username = str(author_username or "").strip().lower()
    clean_display_name = str(author or "").strip() or clean_username or "Community User"
    if clean_username:
        db_user = AppUserModel.objects.filter(username=clean_username).first()
        if db_user:
            if clean_display_name and db_user.display_name != clean_display_name:
                db_user.display_name = clean_display_name
                db_user.save(update_fields=["display_name", "updated_at"])
            return db_user

        db_user = AppUserModel.objects.create(
            username=clean_username,
            email=f"{clean_username}@seed.local",
            password_hash="",
            display_name=clean_display_name,
            role="member",
            account_status="active",
            seller_request_status="none",
        )
        return db_user

    fallback_username = f"community-{abs(hash(clean_display_name.lower())) % 10_000_000}"
    db_user, _ = AppUserModel.objects.get_or_create(
        username=fallback_username,
        defaults={
            "email": f"{fallback_username}@seed.local",
            "password_hash": "",
            "display_name": clean_display_name,
            "role": "member",
            "account_status": "active",
            "seller_request_status": "none",
        },
    )
    if clean_display_name and db_user.display_name != clean_display_name:
        db_user.display_name = clean_display_name
        db_user.save(update_fields=["display_name", "updated_at"])
    return db_user


def _db_reply_to_record(reply: CommunityReplyModel) -> Dict[str, Any]:
    # ORM reply 轉回前端熟悉的 dict 形狀，讓貼文詳情與列表可共用同一份資料格式。
    return {
        "id": int(reply.id),
        "author": str(reply.author_display_name_snapshot or reply.author.display_name or reply.author.username),
        "author_username": _legacy_username(reply.author),
        "author_user_id": reply.author_id,
        "body": str(reply.body or ""),
        "created_at": reply.created_at.isoformat() if reply.created_at else "",
    }


def _legacy_post_to_record(post: Dict[str, Any]) -> Dict[str, Any]:
    # 舊 JSON 貼文資料先正規化欄位名稱與型別，再交給後續裝飾流程。
    replies = []
    for reply in post.get("replies", []) or []:
        replies.append(
            {
                "id": int(reply.get("id", 0) or 0),
                "author": str(reply.get("author") or ""),
                "author_username": str(reply.get("author_username") or "").strip().lower() or None,
                "author_user_id": reply.get("author_user_id"),
                "body": str(reply.get("body") or ""),
                "created_at": str(reply.get("created_at") or ""),
            }
        )
    return {
        "id": int(post.get("id", 0) or 0),
        "topic": str(post.get("topic") or "general"),
        "author": str(post.get("author") or ""),
        "author_username": str(post.get("author_username") or "").strip().lower() or None,
        "author_user_id": post.get("author_user_id"),
        "title": str(post.get("title") or ""),
        "body": str(post.get("body") or ""),
        "tags": [str(tag).strip().lower() for tag in post.get("tags") or [] if str(tag).strip()],
        "votes": int(post.get("votes", 0) or 0),
        "created_at": str(post.get("created_at") or ""),
        "updated_at": str(post.get("updated_at") or ""),
        "replies": replies,
    }


def _db_post_to_record(post: CommunityPostModel) -> Dict[str, Any]:
    # ORM 貼文轉成 canonical payload，回覆在這裡一併展開成前端可直接渲染的陣列。
    replies = [
        _db_reply_to_record(reply)
        for reply in post.replies.filter(is_visible=True).select_related("author").order_by("id")
    ]
    return {
        "id": int(post.id),
        "topic": str(post.topic or "general"),
        "author": str(post.author_display_name_snapshot or post.author.display_name or post.author.username),
        "author_username": _legacy_username(post.author),
        "author_user_id": post.author_id,
        "title": str(post.title or ""),
        "body": str(post.body_html or ""),
        "tags": [tag.strip().lower() for tag in str(getattr(post, "_legacy_tags_csv", "") or "").split(",") if tag.strip()],
        "votes": int(post.votes_count or 0),
        "created_at": post.created_at.isoformat() if post.created_at else "",
        "updated_at": post.updated_at.isoformat() if post.updated_at else "",
        "replies": replies,
    }


def _decorate_public_post(post: Dict[str, Any]) -> Dict[str, Any]:
    # 公開社群 API 需要補顯示欄位，並保留原作者名稱給前端直接展示。
    item = dict(post)
    item["created_at_display"] = _format_created_at(item.get("created_at", ""))
    item["author_user_id"] = _resolve_author_user_id(item.get("author_user_id"), item.get("author_username"))
    replies = []
    for reply in item.get("replies", []):
        reply_item = dict(reply)
        reply_item["created_at_display"] = _format_created_at(reply_item.get("created_at", ""))
        reply_item["author_user_id"] = _resolve_author_user_id(
            reply_item.get("author_user_id"),
            reply_item.get("author_username"),
        )
        reply_item["author"] = anonymize_public_name(str(reply_item.get("author", "")))
        replies.append(reply_item)
    item["replies"] = replies
    item["reply_count"] = len(replies)
    return item


def list_voted_post_ids(*, username: str | None = None, user_id: int | None = None) -> set[int]:
    # 讓 API 可標示目前使用者已投過票的文章，避免前端只能依賴重新整理判斷狀態。
    try:
        if user_id:
            return {
                int(post_id)
                for post_id in CommunityVoteModel.objects.filter(user_id=user_id).values_list("post_id", flat=True)
            }
        clean_username = str(username or "").strip().lower()
        if not clean_username:
            return set()
        voter = AppUserModel.objects.filter(username=clean_username).only("id").first()
        if not voter:
            return set()
        return {
            int(post_id)
            for post_id in CommunityVoteModel.objects.filter(user_id=voter.id).values_list("post_id", flat=True)
        }
    except _LEGACY_FALLBACK_EXCEPTIONS:
        return set()


def _persist_post_record(post_record: Dict[str, Any]) -> Dict[str, Any]:
    # 無論資料來自 ORM 還是 JSON，寫入後都重新整理成同一份 canonical post payload。
    return {
        "id": int(post_record.get("id", 0)),
        "topic": str(post_record.get("topic") or "general"),
        "author": str(post_record.get("author") or ""),
        "author_username": str(post_record.get("author_username") or "").strip().lower() or None,
        "author_user_id": post_record.get("author_user_id"),
        "title": str(post_record.get("title") or ""),
        "body": str(post_record.get("body") or ""),
        "tags": [str(tag).strip().lower() for tag in post_record.get("tags") or [] if str(tag).strip()],
        "votes": int(post_record.get("votes", 0) or 0),
        "created_at": str(post_record.get("created_at") or ""),
        "updated_at": str(post_record.get("updated_at") or ""),
        "replies": [
            {
                "id": int(reply.get("id", 0) or 0),
                "author": str(reply.get("author") or ""),
                "author_username": str(reply.get("author_username") or "").strip().lower() or None,
                "author_user_id": reply.get("author_user_id"),
                "body": str(reply.get("body") or ""),
                "created_at": str(reply.get("created_at") or ""),
            }
            for reply in (post_record.get("replies") or [])
        ],
    }


def save_editor_image(uploaded_file: UploadedFile) -> str:
    # 社群編輯器圖片上傳只接受常見圖片格式，並限制單檔大小避免濫用。
    if not uploaded_file:
        raise ValueError("Please choose an image file.")

    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Only jpg, jpeg, png, webp, and gif images are allowed.")
    if uploaded_file.size > MAX_IMAGE_SIZE_BYTES:
        raise ValueError("Each image must be 5 MB or smaller.")

    upload_dir = _community_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)

    timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    file_name = f"community-{timestamp}{extension}"
    object_name = f"community/{file_name}"
    if cloud_storage_service.is_enabled():
        uploaded_path = cloud_storage_service.upload_image(uploaded_file, object_name)
        if not uploaded_path:
            raise ValueError("Unable to upload the image to cloud storage.")
        return uploaded_path
    target_path = upload_dir / file_name
    with target_path.open("wb") as output:
        for chunk in uploaded_file.chunks():
            output.write(chunk)

    return f"/static/uploads/community/{file_name}"


def list_posts(topic: Optional[str] = None) -> List[Dict[str, Any]]:
    # 社群首頁讀公開貼文列表；ORM 不可用時才退回 local JSON。
    try:
        queryset = CommunityPostModel.objects.filter(is_visible=True).select_related("author").prefetch_related("replies__author")
        if topic:
            queryset = queryset.filter(topic=topic)
        items = []
        for post in queryset.order_by("-id"):
            items.append(_decorate_public_post(_db_post_to_record(post)))
        return items
    except _LEGACY_FALLBACK_EXCEPTIONS:
        posts = local_store.get_posts()
        if topic:
            posts = [post for post in posts if str(post.get("topic") or "").strip().lower() == topic]
        return [_decorate_public_post(_legacy_post_to_record(post)) for post in posts]


def list_all_posts(topic: Optional[str] = None) -> List[Dict[str, Any]]:
    # 管理端與會員中心需要未匿名化的 canonical payload，所以不走 public decorator。
    try:
        queryset = CommunityPostModel.objects.filter(is_visible=True).select_related("author").prefetch_related("replies__author")
        if topic:
            queryset = queryset.filter(topic=topic)
        return [_db_post_to_record(post) for post in queryset.order_by("-id")]
    except _LEGACY_FALLBACK_EXCEPTIONS:
        posts = local_store.get_posts()
        if topic:
            posts = [post for post in posts if str(post.get("topic") or "").strip().lower() == topic]
        return [_legacy_post_to_record(post) for post in posts]


def get_post_detail(post_id: int) -> Optional[Dict[str, Any]]:
    # 貼文詳情頁回傳單篇公開貼文，包含回覆與匿名化後的作者資訊。
    try:
        post = (
            CommunityPostModel.objects.filter(id=post_id, is_visible=True)
            .select_related("author")
            .prefetch_related("replies__author")
            .first()
        )
        if not post:
            return None
        return _decorate_public_post(_db_post_to_record(post))
    except _LEGACY_FALLBACK_EXCEPTIONS:
        post = local_store.get_post_by_id(post_id)
        if not post:
            return None
        return _decorate_public_post(_legacy_post_to_record(post))


def summarize_posts(topic: Optional[str] = None) -> Dict[str, int]:
    # 社群首頁統計只關心貼文與回覆數量，直接從 public post 列表推導即可。
    posts = list_posts(topic)
    return {
        "post_count": len(posts),
        "reply_count": sum(post["reply_count"] for post in posts),
    }


def create_post(
    *,
    topic: str,
    author: str,
    title: str,
    body: str,
    tags: str,
    author_username: str | None = None,
    author_user_id: int | None = None,
) -> Dict[str, Any]:
    # 建立貼文同時支援 ORM 與 JSON fallback，回傳 canonical payload 讓前端可直接插入列表。
    topic = topic.strip().lower() or "general"
    author = author.strip()
    title = title.strip()
    body = body.strip()

    if not author:
        raise ValueError("Please enter your name.")
    if not title:
        raise ValueError("Please enter a post title.")
    if not body:
        raise ValueError("Please enter your post content.")

    tag_list = [tag.strip().lower() for tag in tags.split(",") if tag.strip()]
    clean_username = str(author_username or "").strip().lower() or None
    resolved_user_id = _resolve_author_user_id(author_user_id, clean_username)

    try:
        db_author = _get_or_create_author(author_username, author)
        post = CommunityPostModel.objects.create(
            author=db_author,
            author_display_name_snapshot=author,
            topic=topic,
            title=title,
            body_html=body,
            votes_count=0,
            is_visible=True,
        )
        post._legacy_tags_csv = ",".join(tag_list)
        return _persist_post_record(_db_post_to_record(post))
    except _LEGACY_FALLBACK_EXCEPTIONS:
        posts = list(local_store.get_posts())
        next_id = max((int(item.get("id", 0) or 0) for item in posts), default=0) + 1
        now_iso = timezone.now().isoformat()
        record = _persist_post_record(
            {
                "id": next_id,
                "topic": topic,
                "author": author,
                "author_username": clean_username,
                "author_user_id": resolved_user_id,
                "title": title,
                "body": body,
                "tags": tag_list,
                "votes": 0,
                "created_at": now_iso,
                "updated_at": now_iso,
                "replies": [],
            }
        )
        posts.append(record)
        local_store.save_posts(posts)
        return record


def _is_post_owner(post: Dict[str, Any], *, username: str | None = None, user_id: int | None = None) -> bool:
    # 編輯 / 刪除權限優先比 username，再退回比 user_id，兼容舊貼文缺欄位的情況。
    post_username = str(post.get("author_username") or "").strip().lower()
    current_username = str(username or "").strip().lower()
    if post_username and current_username and post_username == current_username:
        return True

    post_user_id = post.get("author_user_id")
    if post_user_id is not None and user_id is not None and str(post_user_id) == str(user_id):
        return True

    return False


def _normalize_post_input(*, topic: str, title: str, body: str, tags: str) -> Dict[str, Any]:
    # 建立與編輯貼文共用同一套輸入清理規則，避免前後驗證分岔。
    normalized_topic = topic.strip().lower() or "general"
    normalized_title = title.strip()
    normalized_body = body.strip()

    if not normalized_title:
        raise ValueError("Please enter a post title.")
    if not normalized_body:
        raise ValueError("Please enter your post content.")

    return {
        "topic": normalized_topic,
        "title": normalized_title,
        "body": normalized_body,
        "tags": [tag.strip().lower() for tag in tags.split(",") if tag.strip()],
    }


def update_post(
    *,
    post_id: int,
    username: str,
    user_id: int | None,
    topic: str,
    title: str,
    body: str,
    tags: str,
) -> Dict[str, Any]:
    # 只允許貼文作者更新內容；ORM / JSON 兩條路都回傳同一份標準化結果。
    normalized = _normalize_post_input(topic=topic, title=title, body=body, tags=tags)

    try:
        post = (
            CommunityPostModel.objects.filter(id=post_id, is_visible=True)
            .select_related("author")
            .prefetch_related("replies__author")
            .first()
        )
        if not post:
            raise ValueError("Post not found.")
        record = _db_post_to_record(post)
        if not _is_post_owner(record, username=username, user_id=user_id):
            raise PermissionError("You can only edit your own post.")
        post.topic = normalized["topic"]
        post.title = normalized["title"]
        post.body_html = normalized["body"]
        post.save()
        post._legacy_tags_csv = ",".join(normalized["tags"])
        return _persist_post_record(_db_post_to_record(post))
    except _LEGACY_FALLBACK_EXCEPTIONS:
        posts = list(local_store.get_posts())
        updated_record = None
        for index, item in enumerate(posts):
            if int(item.get("id", 0) or 0) != int(post_id):
                continue
            record = _legacy_post_to_record(item)
            if not _is_post_owner(record, username=username, user_id=user_id):
                raise PermissionError("You can only edit your own post.")
            item["topic"] = normalized["topic"]
            item["title"] = normalized["title"]
            item["body"] = normalized["body"]
            item["tags"] = normalized["tags"]
            item["updated_at"] = timezone.now().isoformat()
            updated_record = _persist_post_record(item)
            posts[index] = updated_record
            break
        if updated_record is None:
            raise ValueError("Post not found.")
        local_store.save_posts(posts)
        return updated_record


def delete_post(
    *,
    post_id: int,
    username: str = "",
    user_id: int | None = None,
    enforce_owner: bool = True,
) -> None:
    # 刪文預設會檢查作者身分；管理端可透過 `enforce_owner=False` 略過這層限制。
    try:
        post = CommunityPostModel.objects.filter(id=post_id).select_related("author").first()
        if not post:
            raise ValueError("Post not found.")
        record = _db_post_to_record(post)
        if enforce_owner and not _is_post_owner(record, username=username, user_id=user_id):
            raise PermissionError("You can only delete your own post.")
        post.delete()
    except _LEGACY_FALLBACK_EXCEPTIONS:
        posts = list(local_store.get_posts())
        remaining = []
        removed = None
        for item in posts:
            if int(item.get("id", 0) or 0) == int(post_id):
                removed = _legacy_post_to_record(item)
                continue
            remaining.append(item)
        if removed is None:
            raise ValueError("Post not found.")
        if enforce_owner and not _is_post_owner(removed, username=username, user_id=user_id):
            raise PermissionError("You can only delete your own post.")
        local_store.save_posts(remaining)


def create_reply(
    *,
    post_id: int,
    author: str,
    body: str,
    author_username: str | None = None,
    author_user_id: int | None = None,
) -> Dict[str, Any]:
    # 回覆建立後回傳單筆 reply payload，讓貼文詳情頁可以直接 append。
    author = author.strip()
    body = body.strip()

    if not author:
        raise ValueError("Please enter your name.")
    if not body:
        raise ValueError("Please enter your reply.")

    clean_username = str(author_username or "").strip().lower() or None
    resolved_user_id = _resolve_author_user_id(author_user_id, clean_username)

    try:
        post = CommunityPostModel.objects.filter(id=post_id, is_visible=True).select_related("author").first()
        if not post:
            raise ValueError("Post not found.")
        db_author = _get_or_create_author(author_username, author)
        reply = CommunityReplyModel.objects.create(
            post=post,
            author=db_author,
            author_display_name_snapshot=author,
            body=body,
            is_visible=True,
        )
        persisted = _persist_post_record(_db_post_to_record(post))
        for item in persisted.get("replies", []):
            if int(item.get("id", 0) or 0) == int(reply.id):
                return item
        return _db_reply_to_record(reply)
    except _LEGACY_FALLBACK_EXCEPTIONS:
        posts = list(local_store.get_posts())
        created_reply = None
        for item in posts:
            if int(item.get("id", 0) or 0) != int(post_id):
                continue
            replies = list(item.get("replies", []) or [])
            next_id = max((int(reply.get("id", 0) or 0) for reply in replies), default=0) + 1
            created_reply = {
                "id": next_id,
                "author": author,
                "author_username": clean_username,
                "author_user_id": resolved_user_id,
                "body": body,
                "created_at": timezone.now().isoformat(),
            }
            replies.append(created_reply)
            item["replies"] = replies
            item["updated_at"] = timezone.now().isoformat()
            break
        if created_reply is None:
            raise ValueError("Post not found.")
        local_store.save_posts(posts)
        return _persist_post_record({"replies": [created_reply]}).get("replies", [created_reply])[0]


def upvote_post(post_id: int, *, username: str | None = None, user_id: int | None = None) -> Dict[str, Any]:
    # 已登入使用者在 ORM 下會去重複投票；訪客或 fallback JSON 則採單純累加。
    try:
        post = CommunityPostModel.objects.filter(id=post_id, is_visible=True).select_related("author").first()
        if not post:
            raise ValueError("Post not found.")
        if username or user_id:
            voter = None
            if user_id:
                voter = AppUserModel.objects.filter(id=user_id).first()
            if not voter and username:
                voter = _get_or_create_author(username, username)
            if voter:
                _, created = CommunityVoteModel.objects.get_or_create(post=post, user=voter, defaults={"value": 1})
                if created:
                    post.votes_count = int(post.votes_count or 0) + 1
                    post.save(update_fields=["votes_count", "updated_at"])
            else:
                post.votes_count = int(post.votes_count or 0) + 1
                post.save(update_fields=["votes_count", "updated_at"])
        else:
            post.votes_count = int(post.votes_count or 0) + 1
            post.save(update_fields=["votes_count", "updated_at"])
        return _persist_post_record(_db_post_to_record(post))
    except _LEGACY_FALLBACK_EXCEPTIONS:
        posts = list(local_store.get_posts())
        updated = None
        for item in posts:
            if int(item.get("id", 0) or 0) != int(post_id):
                continue
            item["votes"] = int(item.get("votes", 0) or 0) + 1
            item["updated_at"] = timezone.now().isoformat()
            updated = _persist_post_record(item)
            break
        if updated is None:
            raise ValueError("Post not found.")
        local_store.save_posts(posts)
        return updated
