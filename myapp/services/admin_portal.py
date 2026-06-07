"""後台儀表板與內容管理共用的 service helper。

這層負責把商品、評論、問答、社群貼文、訂單摘要整理成後台頁面
可直接使用的列表與統計格式，避免 view 再自行拼裝欄位。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..repositories import local_store
from . import auth_demo
from . import community as community_service
from . import orders
from . import product_management
from . import questions as question_service
from . import reviews as review_service


def _format_datetime(value: str) -> str:
    # 後台列表只需要簡短時間字串，這裡統一把 ISO datetime 轉成本地顯示格式。
    parsed = parse_datetime(value) if value else None
    if not parsed:
        return ""
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M")


def _status_sort_key(product: Dict[str, Any]) -> tuple[int, str]:
    # 商品清單要先依狀態分組，再依更新時間排序，這裡提供可重複使用的排序 key。
    status = str(product.get("status", "draft"))
    order = {"active": 0, "draft": 1, "archived": 2}.get(status, 9)
    return order, str(product.get("updated_at") or product.get("created_at") or "")


def _normalize_admin_product(product: Dict[str, Any]) -> Dict[str, Any]:
    # 後台商品卡片沿用前台 prepare 過的欄位，再補上管理端專用的賣家與時間顯示欄位。
    item = product_management.prepare_product_for_display(product)
    item["created_at_display"] = _format_datetime(str(item.get("created_at") or ""))
    item["updated_at_display"] = _format_datetime(str(item.get("updated_at") or ""))
    item["seller_display_name"] = str(item.get("owner_display_name") or "")
    item["seller_username"] = str(item.get("owner_username") or "")
    return item


def _resolve_product(product_id: int | None = None, slug: str = "") -> Dict[str, Any] | None:
    # 評論 / 問答摘要常常只有 product_id，後台管理頁則常用 slug；這裡統一補齊商品資料。
    if slug:
        product = product_management.get_product_for_admin(slug)
        if product:
            return _normalize_admin_product(product)
    if product_id is not None:
        for product in product_management.list_products_for_admin():
            if int(product.get("id", 0) or 0) == int(product_id):
                return _normalize_admin_product(product)
    return None


def _review_summary(review: Dict[str, Any]) -> Dict[str, Any]:
    # 後台評論列表需要能直接跳回商品頁與管理頁，所以在這裡把關聯資訊一併展開。
    product = _resolve_product(product_id=review.get("product_id"))
    return {
        "id": int(review.get("id", 0)),
        "title": str(review.get("title") or "").strip() or "Untitled review",
        "body": str(review.get("body") or ""),
        "rating": int(review.get("rating", 0) or 0),
        "author": str(review.get("author") or ""),
        "author_username": str(review.get("author_username") or ""),
        "created_at": str(review.get("created_at") or ""),
        "created_at_display": _format_datetime(str(review.get("created_at") or "")),
        "product_id": product.get("id") if product else review.get("product_id"),
        "product_slug": product.get("slug") if product else "",
        "product_name": product.get("name") if product else "",
        "source_url": f"/products/{product['slug']}" if product else "",
        "management_url": "/staff/content/reviews",
    }


def _question_summary(question: Dict[str, Any]) -> Dict[str, Any]:
    # 問答管理除了基本文字，還要預先算出是否已回覆與答案數量，方便前端直接渲染篩選結果。
    product = _resolve_product(product_id=question.get("product_id"))
    answers = question.get("answers") or []
    return {
        "id": int(question.get("id", 0)),
        "title": str(question.get("title") or "").strip() or "Untitled question",
        "body": str(question.get("body") or ""),
        "author": str(question.get("author") or ""),
        "author_username": str(question.get("author_username") or ""),
        "created_at": str(question.get("created_at") or ""),
        "created_at_display": _format_datetime(str(question.get("created_at") or "")),
        "answer_count": len(answers),
        "is_answered": bool(answers),
        "product_id": product.get("id") if product else question.get("product_id"),
        "product_slug": product.get("slug") if product else "",
        "product_name": product.get("name") if product else "",
        "source_url": f"/products/{product['slug']}" if product else "",
        "management_url": "/staff/content/questions",
    }


def _post_summary(post: Dict[str, Any]) -> Dict[str, Any]:
    # 社群貼文後台清單只保留管理所需欄位，避免把完整 thread payload 直接丟到列表頁。
    replies = post.get("replies") or []
    return {
        "id": int(post.get("id", 0)),
        "topic": str(post.get("topic") or "general"),
        "title": str(post.get("title") or "").strip() or "Untitled post",
        "body": str(post.get("body") or ""),
        "author": str(post.get("author") or ""),
        "author_username": str(post.get("author_username") or ""),
        "created_at": str(post.get("created_at") or ""),
        "created_at_display": _format_datetime(str(post.get("created_at") or "")),
        "reply_count": len(replies),
        "source_url": f"/community/{int(post.get('id', 0))}",
        "management_url": "/staff/content/posts",
    }


def list_admin_products(
    *,
    q: str = "",
    status: str = "",
    category: str = "",
    brand: str = "",
    owner: str = "",
) -> list[Dict[str, Any]]:
    # 後台商品列表支援多欄位模糊搜尋與狀態篩選，這裡回傳已排序完成的最終列表。
    search_value = q.strip().lower()
    status_value = status.strip().lower()
    category_value = category.strip().lower()
    brand_value = brand.strip().lower()
    owner_value = owner.strip().lower()

    items: list[Dict[str, Any]] = []
    for product in product_management.list_products_for_admin():
        item = _normalize_admin_product(product)
        haystacks = [
            str(item.get("name") or "").lower(),
            str(item.get("slug") or "").lower(),
            str(item.get("brand") or "").lower(),
            str(item.get("category") or "").lower(),
            str(item.get("seller_display_name") or "").lower(),
            str(item.get("seller_username") or "").lower(),
        ]
        if search_value and not any(search_value in value for value in haystacks):
            continue
        if status_value and str(item.get("status") or "").lower() != status_value:
            continue
        if category_value and str(item.get("category_slug") or "").lower() != category_value:
            continue
        if brand_value and str(item.get("brand") or "").lower() != brand_value:
            continue
        if owner_value and owner_value not in haystacks[-2] and owner_value not in haystacks[-1]:
            continue
        items.append(item)

    items.sort(key=lambda item: str(item.get("name") or "").lower())
    items.sort(
        key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
        reverse=True,
    )
    items.sort(key=lambda item: _status_sort_key(item)[0])
    return items


def list_admin_reviews(*, q: str = "", rating: str = "") -> list[Dict[str, Any]]:
    # 評論管理頁的搜尋來源包含標題、內容、作者與商品名稱，避免前端重做關鍵字組裝。
    search_value = q.strip().lower()
    rating_value = rating.strip()

    items = []
    for review in review_service.list_all_reviews():
        item = _review_summary(review)
        haystacks = [
            item["title"].lower(),
            item["body"].lower(),
            item["author"].lower(),
            str(item.get("product_name") or "").lower(),
        ]
        if search_value and not any(search_value in value for value in haystacks):
            continue
        if rating_value and str(item.get("rating")) != rating_value:
            continue
        items.append(item)

    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items


def list_admin_questions(*, q: str = "", answered: str = "") -> list[Dict[str, Any]]:
    # answered / unanswered 是 UI 的語意值，這裡先轉成布林條件再套用到清單。
    search_value = q.strip().lower()
    answered_value = answered.strip().lower()

    items = []
    for question in question_service.list_all_questions():
        item = _question_summary(question)
        haystacks = [
            item["title"].lower(),
            item["body"].lower(),
            item["author"].lower(),
            str(item.get("product_name") or "").lower(),
        ]
        if search_value and not any(search_value in value for value in haystacks):
            continue
        if answered_value == "answered" and not item["is_answered"]:
            continue
        if answered_value == "unanswered" and item["is_answered"]:
            continue
        items.append(item)

    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items


def list_admin_posts(*, q: str = "", topic: str = "") -> list[Dict[str, Any]]:
    # 社群貼文管理沿用 community service 的 topic 篩選，再疊上後台自己的全文搜尋。
    search_value = q.strip().lower()
    topic_value = topic.strip().lower()

    items = []
    for post in community_service.list_all_posts(topic=topic_value or None):
        item = _post_summary(post)
        haystacks = [
            item["title"].lower(),
            item["body"].lower(),
            item["author"].lower(),
            item["topic"].lower(),
        ]
        if search_value and not any(search_value in value for value in haystacks):
            continue
        items.append(item)

    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items


def delete_review(review_id: int) -> None:
    # 後台刪除直接委派給原始 service，這裡只保留入口讓 admin view 維持一致呼叫方式。
    review_service.delete_review(review_id)


def delete_question(question_id: int) -> None:
    # 問答刪除同樣透過原 service 執行，避免後台複製刪除邏輯。
    question_service.delete_question(question_id)


def delete_post(post_id: int) -> None:
    # 管理者可略過作者限制強制刪文，所以這裡固定帶 `enforce_owner=False`。
    community_service.delete_post(post_id=post_id, enforce_owner=False)


def build_dashboard() -> Dict[str, Any]:
    # 儀表板首頁只需要聚合數字與最近內容，不需要完整管理列表，這裡一次整理所有卡片資料。
    users = auth_demo.list_users()
    products = list_admin_products()
    review_items = list_admin_reviews()
    question_items = list_admin_questions()
    post_items = list_admin_posts()
    order_summary = orders.build_admin_order_summary()

    return {
        "users": {
            "total": len(users),
            "active": len(
                [
                    user
                    for user in users
                    if user.get("account_status", auth_demo.ACCOUNT_STATUS_ACTIVE)
                    == auth_demo.ACCOUNT_STATUS_ACTIVE
                ]
            ),
            "suspended": len(
                [user for user in users if user.get("account_status") == auth_demo.ACCOUNT_STATUS_SUSPENDED]
            ),
            "sellers": len([user for user in users if auth_demo.is_seller(user)]),
            "pending_seller_requests": len(auth_demo.list_seller_requests()),
        },
        "products": {
            "total": len(products),
            "active": len([item for item in products if item.get("status") == product_management.ACTIVE_STATUS]),
            "draft": len([item for item in products if item.get("status") == product_management.DRAFT_STATUS]),
            "archived": len([item for item in products if item.get("status") == product_management.ARCHIVED_STATUS]),
        },
        "orders": {
            **order_summary,
            "total": int(order_summary.get("order_count", 0) or 0),
            "pending": int(order_summary.get("pending_service_requests", 0) or 0),
            "completed": int(order_summary.get("confirmed_count", 0) or 0),
        },
        "content": {
            "total": len(review_items) + len(question_items) + len(post_items),
            "reviews": len(review_items),
            "questions": len(question_items),
            "posts": len(post_items),
        },
        "recent_reviews": review_items[:5],
        "recent_questions": question_items[:5],
        "recent_posts": post_items[:5],
    }
