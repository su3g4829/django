"""社群論壇服務模組。

負責文章列表、文章詳情、回覆與按讚等論壇互動流程。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..repositories import local_store


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
    replies = []
    for reply in item.get("replies", []):
        reply_item = dict(reply)
        reply_item["created_at_display"] = _format_created_at(reply_item.get("created_at", ""))
        reply_item["author_user_id"] = _resolve_author_user_id(reply_item.get("author_user_id"), reply_item.get("author_username"))
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
