"""我的內容頁彙整服務模組。

將會員的評論、問答、文章、商品與個人化資料整理成單一儀表板。
"""
from __future__ import annotations

from typing import Any, Dict, List

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..repositories import local_store
from . import orders as order_service
from . import personalization as personalization_service
from . import product_management


def _format_created_at(value: str) -> str:
    """格式化 我的內容頁 流程中使用的時間或顯示值。

    參數:
        value: 待格式化、待解析或待判斷的值。

    回傳:
        依函式用途回傳對應資料。
    """
    parsed = parse_datetime(value) if value else None
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M") if parsed else ""


def _matches_user(item: Dict[str, Any], username: str, display_name: str) -> bool:
    """判斷 我的內容頁 條件是否成立。

    參數:
        item: 單一品項資料。
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        display_name: 前台顯示名稱，用來顯示在頁面或內容作者資訊中。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return item.get("author_username") == username or item.get("author") == display_name


def _product_stub(product_id: int) -> Dict[str, Any] | None:
    """處理 我的內容頁 相關流程。

    參數:
        product_id: 商品整數編號。

    回傳:
        依函式用途回傳對應資料。
    """
    product = local_store.get_product_by_id(product_id)
    if not product:
        return None
    return {
        "id": product["id"],
        "slug": product["slug"],
        "name": product["name"],
    }


def list_user_reviews(username: str, display_name: str) -> List[Dict[str, Any]]:
    """列出 我的內容頁 相關資料，供頁面或 API 顯示。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        display_name: 前台顯示名稱，用來顯示在頁面或內容作者資訊中。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    items = []
    for review in sorted(local_store.get_reviews(), key=lambda item: item.get("created_at", ""), reverse=True):
        if not _matches_user(review, username, display_name):
            continue
        item = dict(review)
        item["created_at_display"] = _format_created_at(item.get("created_at", ""))
        item["product"] = _product_stub(item["product_id"])
        items.append(item)
    return items


def list_user_questions(username: str, display_name: str) -> List[Dict[str, Any]]:
    """列出 我的內容頁 相關資料，供頁面或 API 顯示。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        display_name: 前台顯示名稱，用來顯示在頁面或內容作者資訊中。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    items = []
    for question in sorted(local_store.get_questions(), key=lambda item: item.get("created_at", ""), reverse=True):
        if not _matches_user(question, username, display_name):
            continue
        item = dict(question)
        item["created_at_display"] = _format_created_at(item.get("created_at", ""))
        item["product"] = _product_stub(item["product_id"])
        item["answer_count"] = len(item.get("answers", []))
        items.append(item)
    return items


def list_user_answers(username: str, display_name: str) -> List[Dict[str, Any]]:
    """列出 我的內容頁 相關資料，供頁面或 API 顯示。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        display_name: 前台顯示名稱，用來顯示在頁面或內容作者資訊中。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    items = []
    for question in local_store.get_questions():
        product = _product_stub(question["product_id"])
        for answer in question.get("answers", []):
            if not _matches_user(answer, username, display_name):
                continue
            item = dict(answer)
            item["created_at_display"] = _format_created_at(item.get("created_at", ""))
            item["question_title"] = question["title"]
            item["product"] = product
            items.append(item)
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)


def list_user_posts(username: str, display_name: str) -> List[Dict[str, Any]]:
    """列出 我的內容頁 相關資料，供頁面或 API 顯示。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        display_name: 前台顯示名稱，用來顯示在頁面或內容作者資訊中。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    items = []
    for post in sorted(local_store.get_posts(), key=lambda item: item.get("created_at", ""), reverse=True):
        if not _matches_user(post, username, display_name):
            continue
        item = dict(post)
        item["created_at_display"] = _format_created_at(item.get("created_at", ""))
        item["reply_count"] = len(item.get("replies", []))
        items.append(item)
    return items


def list_user_products(username: str) -> List[Dict[str, Any]]:
    """列出 我的內容頁 相關資料，供頁面或 API 顯示。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    items = []
    for product in product_management.list_products_for_user(username):
        item = dict(product)
        item["created_at_display"] = _format_created_at(item.get("created_at", ""))
        item["updated_at_display"] = _format_created_at(item.get("updated_at", ""))
        items.append(item)
    return items


def build_profile_dashboard(user: Dict[str, str], session) -> Dict[str, Any]:
    """組合會員中心首頁所需的所有內容區塊資料。

    參數:
        user: 目前操作中的會員快照資料。
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    username = user["username"]
    display_name = user["display_name"]
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
