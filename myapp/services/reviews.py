from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List, Optional

from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from ..models import AppUser as AppUserModel
from ..models import Product as ProductModel
from ..models import ProductReview as ProductReviewModel
from .privacy import anonymize_public_name


def _format_created_at(value: str) -> str:
    # 商品頁與後台都用同一種簡短時間顯示，避免各處各自處理 timezone。
    parsed = parse_datetime(value) if value else None
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M") if parsed else ""


def _db_reviews_enabled() -> bool:
    # 評論功能正處於 JSON / ORM 並行期，這裡用來判斷是否可以走資料庫版本。
    try:
        ProductReviewModel.objects.count()
        return True
    except Exception:
        return False


def _product_model_by_id(product_id: int) -> Optional[ProductModel]:
    # 建立評論前要先確認 ORM 商品存在，避免留下無法關聯的 review 記錄。
    if not _db_reviews_enabled():
        return None
    return ProductModel.objects.filter(id=int(product_id)).first()


def _legacy_username(prefix: str, identifier: str, display_name: str) -> str:
    # 舊 JSON 資料可能只有顯示名稱，這裡產生可落地到 `AppUser` 的保底 username。
    base = slugify(str(display_name or "").strip())[:80]
    if not base:
        base = prefix
    return f"{prefix}-{identifier}-{base}".strip("-")[:150]


def _get_or_create_author(
    *,
    author: str,
    author_username: str | None,
    author_user_id: int | None,
    identifier: str,
) -> Optional[AppUserModel]:
    # 評論作者可能來自已登入會員，也可能是舊資料匿名快照；這裡統一補成 ORM user。
    if not _db_reviews_enabled():
        return None
    if author_user_id:
        db_user = AppUserModel.objects.filter(id=int(author_user_id)).first()
        if db_user:
            return db_user
    clean_username = str(author_username or "").strip().lower()
    if clean_username:
        db_user = AppUserModel.objects.filter(username=clean_username).first()
        if db_user:
            return db_user
        from . import auth_demo

        db_user = auth_demo._get_or_bootstrap_db_user(clean_username)
        if db_user:
            return db_user

    fallback_username = _legacy_username("reviewer", identifier, author)
    db_user, _ = AppUserModel.objects.update_or_create(
        username=fallback_username,
        defaults={
            "email": f"{fallback_username}@seed.local",
            "password_hash": make_password(None),
            "display_name": str(author or fallback_username).strip() or fallback_username,
            "role": "member",
            "account_status": "active",
            "seller_request_status": "none",
        },
    )
    return db_user


def _db_review_to_record(review: ProductReviewModel) -> Dict[str, Any]:
    # ORM review 需要轉回前端既有 payload 形狀，並在這裡順手套用作者匿名化規則。
    payload = {
        "id": int(review.id),
        "product_id": int(review.product_id),
        "author": str(review.author_display_name_snapshot or review.author.display_name or review.author.username or ""),
        "author_username": str(review.author.username or ""),
        "author_user_id": int(review.author_id),
        "rating": int(review.rating or 0),
        "title": str(review.title or ""),
        "body": str(review.body or ""),
        "created_at": timezone.localtime(review.created_at).isoformat() if review.created_at else "",
    }
    payload["created_at_display"] = _format_created_at(str(payload["created_at"]))
    payload["author"] = anonymize_public_name(str(payload["author"]))
    return payload


def anonymize_review_author(name: str) -> str:
    # 保留舊 API 入口，讓其他模組仍可單獨呼叫評論作者匿名化邏輯。
    return anonymize_public_name(name)


def list_reviews(product_id: int) -> List[Dict[str, Any]]:
    # 商品詳情頁只看單一商品評論；無論資料源是 ORM 還是 JSON，都回相同欄位。
    return [
        _db_review_to_record(review)
        for review in ProductReviewModel.objects.filter(product_id=product_id, is_visible=True)
        .select_related("author", "product")
        .order_by("-id")
    ]


def list_all_reviews() -> List[Dict[str, Any]]:
    # 後台內容管理需要跨商品評論總表，所以這裡提供不限制 product_id 的版本。
    return [
        _db_review_to_record(review)
        for review in ProductReviewModel.objects.filter(is_visible=True).select_related("author", "product").order_by("-id")
    ]


def summarize_reviews(product_id: int) -> Dict[str, Any]:
    # 商品卡與詳情頁共用評論總數與平均分，集中在這裡避免重複計算。
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
    # 建立評論時同時支援登入會員與舊資料來源，回傳格式固定給商品頁立即插入列表。
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

    created_at = timezone.localtime().isoformat()

    product = _product_model_by_id(product_id)
    if not product:
        raise ValueError("Product not found.")
    db_author = _get_or_create_author(
        author=author,
        author_username=author_username,
        author_user_id=author_user_id,
        identifier=f"review-{product_id}",
    )
    if not db_author:
        raise ValueError("Author not found.")
    db_review = ProductReviewModel.objects.create(
        product=product,
        author=db_author,
        author_display_name_snapshot=author,
        rating=rating,
        title=title,
        body=body,
        is_visible=True,
    )
    return {
        "id": int(db_review.id),
        "product_id": product_id,
        "author": author,
        "author_username": str(db_author.username or author_username or ""),
        "author_user_id": int(db_author.id),
        "rating": rating,
        "title": title,
        "body": body,
        "created_at": timezone.localtime(db_review.created_at).isoformat() if db_review.created_at else created_at,
    }


def delete_review(review_id: int) -> None:
    # 後台與其他管理入口都會走到這裡；找不到目標時維持明確例外訊息。
    found = False
    deleted, _ = ProductReviewModel.objects.filter(id=review_id).delete()
    found = bool(deleted)

    if not found:
        raise ValueError("Review not found.")
