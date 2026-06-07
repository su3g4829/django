"""會員中心 dashboard 聚合 service。

這層專門替 `MeDashboardApi` 整理個人頁需要的資料，包含：
- 使用者自己的評論、提問、回答
- 社群貼文
- 已上架商品
- 訂單
- 收藏與最近瀏覽

回傳格式會盡量維持前端既有 payload 形狀，讓 view 不需要再逐項重組。
"""

from __future__ import annotations

from typing import Any, Dict, List

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..models import Product as ProductModel
from . import community as community_service
from . import orders as order_service
from . import personalization as personalization_service
from . import product_management
from . import questions as question_service
from . import reviews as review_service


def _format_created_at(value: str) -> str:
    # dashboard 卡片只需要簡短時間顯示，這裡統一做 timezone 與字串格式轉換。
    parsed = parse_datetime(value) if value else None
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M") if parsed else ""


def _matches_user(item: Dict[str, Any], username: str, display_name: str) -> bool:
    # 舊資料有些只有顯示名稱、沒有 author_username，所以 username / display_name 兩邊都要比。
    item_username = str(item.get("author_username") or "").strip().lower()
    item_display_name = str(item.get("author") or "").strip()
    clean_username = str(username or "").strip().lower()
    clean_display_name = str(display_name or "").strip()
    return item_username == clean_username or item_display_name == clean_display_name


def _product_stub(product_id: int) -> Dict[str, Any] | None:
    # 個人頁只需要商品最小摘要來做跳轉，不需要把完整商品 payload 全部灌進來。
    try:
        product = ProductModel.objects.filter(id=int(product_id)).first()
    except Exception:
        product = None
    if not product:
        return None
    return {
        "id": int(product.id),
        "slug": str(product.slug),
        "name": str(product.name),
    }


def list_user_reviews(username: str, display_name: str) -> List[Dict[str, Any]]:
    # 蒐集會員自己發表的評論，並補上商品摘要供 dashboard 直接顯示。
    items: List[Dict[str, Any]] = []
    for review in review_service.list_all_reviews():
        if not _matches_user(review, username, display_name):
            continue
        item = dict(review)
        item["created_at_display"] = _format_created_at(str(item.get("created_at", "")))
        item["product"] = _product_stub(int(item.get("product_id", 0) or 0))
        items.append(item)
    return items


def list_user_questions(username: str, display_name: str) -> List[Dict[str, Any]]:
    # 個人頁問答區顯示使用者提出的問題，並預先算出 answer_count。
    items: List[Dict[str, Any]] = []
    for question in question_service.list_all_questions():
        if not _matches_user(question, username, display_name):
            continue
        item = dict(question)
        item["created_at_display"] = _format_created_at(str(item.get("created_at", "")))
        item["product"] = _product_stub(int(item.get("product_id", 0) or 0))
        item["answer_count"] = len(item.get("answers", []))
        items.append(item)
    return items


def list_user_answers(username: str, display_name: str) -> List[Dict[str, Any]]:
    # 回答是巢狀掛在 question 底下，這裡攤平成 dashboard 比較容易渲染的列表格式。
    items: List[Dict[str, Any]] = []
    for question in question_service.list_all_questions():
        product = _product_stub(int(question.get("product_id", 0) or 0))
        for answer in question.get("answers", []):
            if not _matches_user(answer, username, display_name):
                continue
            item = dict(answer)
            item["created_at_display"] = _format_created_at(str(item.get("created_at", "")))
            item["question_title"] = str(question.get("title") or "")
            item["product"] = product
            items.append(item)
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)


def list_user_posts(username: str, display_name: str) -> List[Dict[str, Any]]:
    # 社群貼文區只保留 dashboard 需要的欄位，回覆數在這裡先整理好。
    items: List[Dict[str, Any]] = []
    for post in community_service.list_all_posts():
        if not _matches_user(post, username, display_name):
            continue
        item = dict(post)
        item["created_at_display"] = _format_created_at(str(item.get("created_at", "")))
        item["reply_count"] = len(item.get("replies", []))
        items.append(item)
    return items


def list_user_products(username: str) -> List[Dict[str, Any]]:
    # 賣家會員中心會顯示自己建立的商品清單，時間欄位在這裡轉成顯示格式。
    items: List[Dict[str, Any]] = []
    for product in product_management.list_products_for_user(username):
        item = dict(product)
        item["created_at_display"] = _format_created_at(str(item.get("created_at", "")))
        item["updated_at_display"] = _format_created_at(str(item.get("updated_at", "")))
        items.append(item)
    return items


def build_profile_dashboard(user: Dict[str, str], session) -> Dict[str, Any]:
    # 會員中心首頁一次組好所有分頁資料，避免 API 端點拆太細造成前端多次請求。
    username = str(user["username"])
    display_name = str(user["display_name"])
    return {
        "reviews": list_user_reviews(username, display_name),
        "questions": list_user_questions(username, display_name),
        "answers": list_user_answers(username, display_name),
        "posts": list_user_posts(username, display_name),
        "owned_products": list_user_products(username),
        "orders": order_service.list_orders_for_user(username),
        "favorite_products": personalization_service.get_favorite_products(session),
        "recent_products": personalization_service.get_recent_products(session),
    }
