"""Admin portal aggregation and management helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..repositories import local_store
from . import auth_demo
from . import orders
from . import product_management


def _format_datetime(value: str) -> str:
    parsed = parse_datetime(value) if value else None
    if not parsed:
        return ""
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M")


def _status_sort_key(product: Dict[str, Any]) -> tuple[int, str]:
    status = str(product.get("status", "draft"))
    order = {"active": 0, "draft": 1, "archived": 2}.get(status, 9)
    return order, str(product.get("updated_at") or product.get("created_at") or "")


def _normalize_admin_product(product: Dict[str, Any]) -> Dict[str, Any]:
    item = product_management.prepare_product_for_display(product)
    item["created_at_display"] = _format_datetime(str(item.get("created_at") or ""))
    item["updated_at_display"] = _format_datetime(str(item.get("updated_at") or ""))
    item["seller_display_name"] = str(item.get("owner_display_name") or "")
    item["seller_username"] = str(item.get("owner_username") or "")
    return item


def _resolve_product(product_id: int | None = None, slug: str = "") -> Dict[str, Any] | None:
    if slug:
        product = local_store.get_product_by_slug(slug)
        if product:
            return _normalize_admin_product(product)
    if product_id is not None:
        product = local_store.get_product_by_id(int(product_id))
        if product:
            return _normalize_admin_product(product)
    return None


def _review_summary(review: Dict[str, Any]) -> Dict[str, Any]:
    product = _resolve_product(product_id=review.get("product_id"))
    return {
        "id": int(review.get("id", 0)),
        "title": str(review.get("title") or "").strip() or "未命名評論",
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
    product = _resolve_product(product_id=question.get("product_id"))
    answers = question.get("answers") or []
    return {
        "id": int(question.get("id", 0)),
        "title": str(question.get("title") or "").strip() or "未命名提問",
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
    replies = post.get("replies") or []
    return {
        "id": int(post.get("id", 0)),
        "topic": str(post.get("topic") or "general"),
        "title": str(post.get("title") or "").strip() or "未命名文章",
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
    search_value = q.strip().lower()
    status_value = status.strip().lower()
    category_value = category.strip().lower()
    brand_value = brand.strip().lower()
    owner_value = owner.strip().lower()

    items: list[Dict[str, Any]] = []
    for product in local_store.get_products():
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
        if category_value and str(item.get("category") or "").lower() != category_value:
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
    search_value = q.strip().lower()
    rating_value = rating.strip()

    items = []
    for review in local_store.get_reviews():
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
    search_value = q.strip().lower()
    answered_value = answered.strip().lower()

    items = []
    for question in local_store.get_questions():
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
    search_value = q.strip().lower()
    topic_value = topic.strip().lower()

    items = []
    for post in local_store.get_posts():
        item = _post_summary(post)
        haystacks = [
            item["title"].lower(),
            item["body"].lower(),
            item["author"].lower(),
            item["topic"].lower(),
        ]
        if search_value and not any(search_value in value for value in haystacks):
            continue
        if topic_value and item["topic"].lower() != topic_value:
            continue
        items.append(item)

    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items


def delete_review(review_id: int) -> None:
    reviews = deepcopy(local_store.get_reviews())
    remaining = [item for item in reviews if int(item.get("id", 0)) != review_id]
    if len(remaining) == len(reviews):
        raise ValueError("Review not found.")
    local_store.save_reviews(remaining)


def delete_question(question_id: int) -> None:
    questions = deepcopy(local_store.get_questions())
    remaining = [item for item in questions if int(item.get("id", 0)) != question_id]
    if len(remaining) == len(questions):
        raise ValueError("Question not found.")
    local_store.save_questions(remaining)


def delete_post(post_id: int) -> None:
    posts = deepcopy(local_store.get_posts())
    remaining = [item for item in posts if int(item.get("id", 0)) != post_id]
    if len(remaining) == len(posts):
        raise ValueError("Post not found.")
    local_store.save_posts(remaining)


def build_dashboard() -> Dict[str, Any]:
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
