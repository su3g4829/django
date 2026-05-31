from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..repositories import local_store
from .privacy import anonymize_public_name


def _resolve_author_user_id(author_user_id: int | None, author_username: str | None) -> int | None:
    if author_user_id:
        return int(author_user_id)
    if not author_username:
        return None
    user = local_store.get_user_by_username(author_username)
    return int(user["id"]) if user else None


def anonymize_review_author(name: str) -> str:
    return anonymize_public_name(name)


def list_reviews(product_id: int) -> List[Dict[str, Any]]:
    reviews = []
    for review in local_store.get_reviews_by_product_id(product_id):
        item = dict(review)
        parsed = parse_datetime(item["created_at"]) if item.get("created_at") else None
        item["created_at_display"] = timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M") if parsed else ""
        item["author_user_id"] = _resolve_author_user_id(item.get("author_user_id"), item.get("author_username"))
        item["author"] = anonymize_review_author(str(item.get("author", "")))
        reviews.append(item)
    return reviews


def summarize_reviews(product_id: int) -> Dict[str, Any]:
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
    author = author.strip()
    title = title.strip()
    body = body.strip()

    if not author:
        raise ValueError("Please enter your name.")
    if rating < 1 or rating > 5:
        raise ValueError("Rating must be between 1 and 5.")
    if not title:
        raise ValueError("Please enter a review title.")
    if not body:
        raise ValueError("Please enter your review.")

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
