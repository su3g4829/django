"""社群論壇服務模組。

負責文章列表、文章詳情、回覆與按讚等論壇互動流程。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..repositories import local_store
from .privacy import anonymize_public_name

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _format_created_at(value: str) -> str:
    """格式化 社群論壇 流程中使用的時間或顯示值。

    參數:
        value: 待格式化、待解析或待判斷的值。

    回傳:
        依函式用途回傳對應資料。
    """
    parsed = parse_datetime(value) if value else None
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M") if parsed else ""


def _resolve_author_user_id(author_user_id: int | None, author_username: str | None) -> int | None:
    """若舊資料沒有 author_user_id，改用 username 補推。"""
    if author_user_id:
        return int(author_user_id)
    if not author_username:
        return None
    user = local_store.get_user_by_username(author_username)
    return int(user["id"]) if user else None


def _community_upload_dir() -> Path:
    return Path(settings.BASE_DIR) / "static" / "uploads" / "community"


def save_editor_image(uploaded_file: UploadedFile) -> str:
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
    target_path = upload_dir / file_name
    with target_path.open("wb") as output:
        for chunk in uploaded_file.chunks():
            output.write(chunk)

    return f"/static/uploads/community/{file_name}"


def list_posts(topic: Optional[str] = None) -> List[Dict[str, Any]]:
    """列出 社群論壇 相關資料，供頁面或 API 顯示。

    參數:
        topic: 論壇主題分類，用來過濾文章列表。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    posts = local_store.get_posts()
    if topic:
        posts = [post for post in posts if post.get("topic") == topic]

    items = []
    for post in sorted(posts, key=lambda item: item.get("created_at", ""), reverse=True):
        item = dict(post)
        item["created_at_display"] = _format_created_at(item.get("created_at", ""))
        item["author_user_id"] = _resolve_author_user_id(item.get("author_user_id"), item.get("author_username"))
        item["author"] = anonymize_public_name(str(item.get("author", "")))
        item["reply_count"] = len(item.get("replies", []))
        items.append(item)
    return items


def get_post_detail(post_id: int) -> Optional[Dict[str, Any]]:
    """取得 社群論壇 流程中指定條件的資料。

    參數:
        post_id: 論壇文章編號。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    post = local_store.get_post_by_id(post_id)
    if not post:
        return None

    item = dict(post)
    item["created_at_display"] = _format_created_at(item.get("created_at", ""))
    item["author_user_id"] = _resolve_author_user_id(item.get("author_user_id"), item.get("author_username"))
    item["author"] = anonymize_public_name(str(item.get("author", "")))
    replies = []
    for reply in item.get("replies", []):
        reply_item = dict(reply)
        reply_item["created_at_display"] = _format_created_at(reply_item.get("created_at", ""))
        reply_item["author_user_id"] = _resolve_author_user_id(reply_item.get("author_user_id"), reply_item.get("author_username"))
        reply_item["author"] = anonymize_public_name(str(reply_item.get("author", "")))
        replies.append(reply_item)
    item["replies"] = replies
    item["reply_count"] = len(replies)
    return item


def summarize_posts(topic: Optional[str] = None) -> Dict[str, int]:
    """處理 社群論壇 相關流程。

    參數:
        topic: 論壇主題分類，用來過濾文章列表。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
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
    """建立新的論壇文章並寫回本地資料。

    參數:
        topic: 論壇主題分類，用來過濾文章列表。
        author: 函式執行所需的輸入資料。
        title: 函式執行所需的輸入資料。
        body: 函式執行所需的輸入資料。
        tags: 函式執行所需的輸入資料。
        author_username: 函式執行所需的輸入資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
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

    posts = local_store.get_posts()
    next_id = max((post["id"] for post in posts), default=0) + 1
    post = {
        "id": next_id,
        "topic": topic,
        "author": author,
        "author_username": author_username,
        "author_user_id": author_user_id,
        "title": title,
        "body": body,
        "tags": tag_list,
        "votes": 0,
        "created_at": timezone.localtime().isoformat(),
        "replies": [],
    }
    posts.append(post)
    local_store.save_posts(posts)
    return post


def _is_post_owner(post: Dict[str, Any], *, username: str | None = None, user_id: int | None = None) -> bool:
    post_username = str(post.get("author_username") or "").strip().lower()
    current_username = str(username or "").strip().lower()
    if post_username and current_username and post_username == current_username:
        return True

    post_user_id = post.get("author_user_id")
    if post_user_id is not None and user_id is not None and str(post_user_id) == str(user_id):
        return True

    return False


def _normalize_post_input(*, topic: str, title: str, body: str, tags: str) -> Dict[str, Any]:
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
    normalized = _normalize_post_input(topic=topic, title=title, body=body, tags=tags)

    posts = local_store.get_posts()
    for post in posts:
        if post.get("id") != post_id:
            continue
        if not _is_post_owner(post, username=username, user_id=user_id):
            raise PermissionError("You can only edit your own post.")

        post["topic"] = normalized["topic"]
        post["title"] = normalized["title"]
        post["body"] = normalized["body"]
        post["tags"] = normalized["tags"]
        post["updated_at"] = timezone.localtime().isoformat()
        local_store.save_posts(posts)
        return post

    raise ValueError("Post not found.")


def delete_post(*, post_id: int, username: str, user_id: int | None) -> None:
    posts = local_store.get_posts()
    for index, post in enumerate(posts):
        if post.get("id") != post_id:
            continue
        if not _is_post_owner(post, username=username, user_id=user_id):
            raise PermissionError("You can only delete your own post.")

        del posts[index]
        local_store.save_posts(posts)
        return

    raise ValueError("Post not found.")


def create_reply(
    *,
    post_id: int,
    author: str,
    body: str,
    author_username: str | None = None,
    author_user_id: int | None = None,
) -> Dict[str, Any]:
    """在指定論壇文章下建立回覆。

    參數:
        post_id: 論壇文章編號。
        author: 函式執行所需的輸入資料。
        body: 函式執行所需的輸入資料。
        author_username: 函式執行所需的輸入資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    author = author.strip()
    body = body.strip()

    if not author:
        raise ValueError("Please enter your name.")
    if not body:
        raise ValueError("Please enter your reply.")

    posts = local_store.get_posts()
    for post in posts:
        if post.get("id") != post_id:
            continue

        replies = post.setdefault("replies", [])
        next_id = max((reply["id"] for reply in replies), default=0) + 1
        reply = {
            "id": next_id,
            "author": author,
            "author_username": author_username,
            "author_user_id": author_user_id,
            "body": body,
            "created_at": timezone.localtime().isoformat(),
        }
        replies.append(reply)
        local_store.save_posts(posts)
        return reply

    raise ValueError("Post not found.")


def upvote_post(post_id: int) -> Dict[str, Any]:
    """替論壇文章累加按讚數並回傳更新後結果。

    參數:
        post_id: 論壇文章編號。

    回傳:
        依函式用途回傳對應資料。
    """
    posts = local_store.get_posts()
    for post in posts:
        if post.get("id") != post_id:
            continue
        post["votes"] = int(post.get("votes", 0)) + 1
        local_store.save_posts(posts)
        return post
    raise ValueError("Post not found.")
