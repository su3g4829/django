"""商品評論服務模組。

負責評論列表、平均評分統計與新增評論驗證。
"""
from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List

from django.utils.dateparse import parse_datetime
from django.utils import timezone

from ..repositories import local_store


def _resolve_author_user_id(author_user_id: int | None, author_username: str | None) -> int | None:
    """若舊資料沒有 author_user_id，改用 username 補推。"""
    if author_user_id:
        return int(author_user_id)
    if not author_username:
        return None
    user = local_store.get_user_by_username(author_username)
    return int(user["id"]) if user else None


def list_reviews(product_id: int) -> List[Dict[str, Any]]:
    """列出 商品評論 相關資料，供頁面或 API 顯示。

    參數:
        product_id: 商品整數編號。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    reviews = []
    for review in local_store.get_reviews_by_product_id(product_id):
        item = dict(review)
        parsed = parse_datetime(item["created_at"]) if item.get("created_at") else None
        item["created_at_display"] = timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M") if parsed else ""
        item["author_user_id"] = _resolve_author_user_id(item.get("author_user_id"), item.get("author_username"))
        reviews.append(item)
    return reviews


def summarize_reviews(product_id: int) -> Dict[str, Any]:
    """處理 商品評論 相關流程。

    參數:
        product_id: 商品整數編號。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    reviews = list_reviews(product_id)
    ratings = [review["rating"] for review in reviews]
    average = round(mean(ratings), 1) if ratings else 0.0
    return {
        "count": len(reviews),
        "average": average,
    }


def create_review(
    *,
    product_id: int,
    author: str,
    rating: int,
    title: str,
    body: str,
    author_username: str | None = None,
    author_user_id: int | None = None,
) -> Dict[str, Any]:
    """建立商品評論並完成基本驗證。

    參數:
        product_id: 商品整數編號。
        author: 函式執行所需的輸入資料。
        rating: 函式執行所需的輸入資料。
        title: 函式執行所需的輸入資料。
        body: 函式執行所需的輸入資料。
        author_username: 函式執行所需的輸入資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    author = author.strip()
    title = title.strip()
    body = body.strip()

    if not author:
        raise ValueError("請輸入評論者名稱")
    if rating < 1 or rating > 5:
        raise ValueError("評分必須介於 1 到 5")
    if not title:
        raise ValueError("請輸入評論標題")
    if not body:
        raise ValueError("請輸入評論內容")

    reviews = local_store.get_reviews()
    next_id = max((review["id"] for review in reviews), default=0) + 1
    created_at = timezone.localtime().isoformat()

    review = {
        "id": next_id,
        "product_id": product_id,
        "author": author,
        "author_username": author_username,
        "author_user_id": author_user_id,
        "rating": rating,
        "title": title,
        "body": body,
        "created_at": created_at,
    }
    reviews.append(review)
    local_store.save_reviews(reviews)
    return review
