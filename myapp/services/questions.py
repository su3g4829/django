from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from ..models import AppUser as AppUserModel
from ..models import Product as ProductModel
from ..models import ProductQuestion as ProductQuestionModel
from ..models import ProductQuestionAnswer as ProductQuestionAnswerModel
from .privacy import anonymize_public_name
MASKED_CONTENT = "****"


def _format_created_at(value: str) -> str:
    # 問答區與後台列表共用相同的建立時間格式，統一集中在 service 處理。
    parsed = parse_datetime(value) if value else None
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M") if parsed else ""


def _db_questions_enabled() -> bool:
    # 商品問答同時有 question / answer 兩張表，兩者都可讀時才切到 ORM 流程。
    try:
        ProductQuestionModel.objects.count()
        ProductQuestionAnswerModel.objects.count()
        return True
    except Exception:
        return False


def _product_model_by_id(product_id: int) -> Optional[ProductModel]:
    # 建立問題前先確認商品存在，避免問答掛到不存在的 product_id。
    if not _db_questions_enabled():
        return None
    return ProductModel.objects.filter(id=int(product_id)).first()


def _legacy_username(prefix: str, identifier: str, display_name: str) -> str:
    # 舊資料缺少正式帳號時，用穩定規則產生 fallback username 以便同步 ORM。
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
    prefix: str,
) -> Optional[AppUserModel]:
    # 問題作者與回答作者都透過這個 helper 補成 `AppUser`，避免兩套建立邏輯分叉。
    if not _db_questions_enabled():
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

    fallback_username = _legacy_username(prefix, identifier, author)
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


def _db_answer_to_record(answer: ProductQuestionAnswerModel) -> Dict[str, Any]:
    # ORM answer 轉成前端問答元件使用的 payload，公開顯示邏輯再由後續 decorator 決定。
    payload = {
        "id": int(answer.id),
        "author": str(answer.author_display_name_snapshot or answer.author.display_name or answer.author.username or ""),
        "author_username": str(answer.author.username or ""),
        "author_user_id": int(answer.author_id),
        "body": str(answer.body or ""),
        "created_at": timezone.localtime(answer.created_at).isoformat() if answer.created_at else "",
    }
    payload["created_at_display"] = _format_created_at(str(payload["created_at"]))
    return payload


def _db_question_to_record(question: ProductQuestionModel) -> Dict[str, Any]:
    # 問題列表要直接帶答案陣列與 answer_count，這裡一次展平成商品頁需要的格式。
    answers = [_db_answer_to_record(answer) for answer in question.answers.filter(is_visible=True).select_related("author").order_by("id")]
    payload = {
        "id": int(question.id),
        "product_id": int(question.product_id),
        "author": str(question.author_display_name_snapshot or question.author.display_name or question.author.username or ""),
        "author_username": str(question.author.username or ""),
        "author_user_id": int(question.author_id),
        "title": str(question.title or ""),
        "body": str(question.body or ""),
        "created_at": timezone.localtime(question.created_at).isoformat() if question.created_at else "",
        "answers": answers,
        "answer_count": len(answers),
    }
    payload["created_at_display"] = _format_created_at(str(payload["created_at"]))
    return payload


def _display_account_name(author: str | None, author_username: str | None) -> str:
    return str(author_username or "").strip() or str(author or "").strip()


def _normalize_user_identity(*, user_id: int | None = None, username: str | None = None) -> Dict[str, Any]:
    return {
        "user_id": int(user_id) if user_id else None,
        "username": str(username or "").strip().lower() or None,
    }


def _is_same_user(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    left_user_id = left.get("user_id")
    right_user_id = right.get("user_id")
    if left_user_id and right_user_id and int(left_user_id) == int(right_user_id):
        return True
    left_username = str(left.get("username") or "").strip().lower()
    right_username = str(right.get("username") or "").strip().lower()
    return bool(left_username and right_username and left_username == right_username)


def _product_owner_identity(product_id: int) -> Dict[str, Any]:
    product = ProductModel.objects.filter(id=int(product_id)).select_related("owner").first()
    if not product:
        return {
            "user_id": None,
            "username": None,
        }
    return {
        "user_id": int(product.owner_id) if product.owner_id else None,
        "username": str(product.owner.username or "").strip().lower() if product.owner_id and product.owner else None,
    }


def _can_view_question_body(*, viewer: Dict[str, Any], question_author: Dict[str, Any], seller: Dict[str, Any]) -> bool:
    return _is_same_user(viewer, question_author) or _is_same_user(viewer, seller)


def _can_view_answer_body(
    *,
    viewer: Dict[str, Any],
    answer_author: Dict[str, Any],
    question_author: Dict[str, Any],
    seller: Dict[str, Any],
) -> bool:
    return _is_same_user(viewer, answer_author) or _can_view_question_body(viewer=viewer, question_author=question_author, seller=seller)


def _decorate_public_answer(
    answer: Dict[str, Any],
    *,
    viewer: Dict[str, Any],
    question_author: Dict[str, Any],
    seller: Dict[str, Any],
) -> Dict[str, Any]:
    item = dict(answer)
    answer_author = _normalize_user_identity(user_id=item.get("author_user_id"), username=item.get("author_username"))
    can_view_body = _can_view_answer_body(viewer=viewer, answer_author=answer_author, question_author=question_author, seller=seller)
    item["author"] = _display_account_name(item.get("author"), item.get("author_username"))
    if not can_view_body:
        item["author"] = anonymize_public_name(item["author"])
    item["is_seller_reply"] = _is_same_user(answer_author, seller)
    item["is_body_masked"] = not can_view_body and bool(str(item.get("body") or "").strip())
    if item["is_body_masked"]:
        item["body"] = MASKED_CONTENT
    return item


def _decorate_public_question(question: Dict[str, Any], *, viewer: Dict[str, Any], seller: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(question)
    question_author = _normalize_user_identity(user_id=item.get("author_user_id"), username=item.get("author_username"))
    can_view_body = _can_view_question_body(viewer=viewer, question_author=question_author, seller=seller)
    item["author"] = _display_account_name(item.get("author"), item.get("author_username"))
    if not can_view_body:
        item["author"] = anonymize_public_name(item["author"])
    item["is_body_masked"] = not can_view_body and bool(str(item.get("body") or "").strip())
    if item["is_body_masked"]:
        item["body"] = MASKED_CONTENT
    item["answers"] = [
        _decorate_public_answer(answer, viewer=viewer, question_author=question_author, seller=seller)
        for answer in item.get("answers", [])
    ]
    item["answer_count"] = len(item["answers"])
    return item


def list_questions(product_id: int, *, viewer_username: str | None = None, viewer_user_id: int | None = None) -> List[Dict[str, Any]]:
    # 商品頁問答區只讀單一商品資料，JSON fallback 也維持與 ORM 相同的輸出結構。
    viewer = _normalize_user_identity(user_id=viewer_user_id, username=viewer_username)
    seller = _product_owner_identity(product_id)
    return [
        _decorate_public_question(_db_question_to_record(question), viewer=viewer, seller=seller)
        for question in ProductQuestionModel.objects.filter(product_id=product_id, is_visible=True)
        .select_related("author", "product")
        .prefetch_related("answers__author")
        .order_by("-id")
    ]


def list_all_questions() -> List[Dict[str, Any]]:
    # 後台內容管理需要跨商品檢視所有問答，這裡提供完整總表。
    return [
        _db_question_to_record(question)
        for question in ProductQuestionModel.objects.filter(is_visible=True)
        .select_related("author", "product")
        .prefetch_related("answers__author")
        .order_by("-id")
    ]


def summarize_questions(product_id: int) -> Dict[str, int]:
    # 商品卡只關心提問數與回答數，不需要整份問答 payload。
    questions = list_questions(product_id)
    return {
        "question_count": len(questions),
        "answer_count": sum(question["answer_count"] for question in questions),
    }


def create_question(
    *,
    product_id: int,
    author: str,
    title: str,
    body: str,
    author_username: str | None = None,
    author_user_id: int | None = None,
) -> Dict[str, Any]:
    # 建立問題後直接回可插入 UI 的 payload，讓商品頁不必額外再查一次。
    author = author.strip()
    title = title.strip()
    body = body.strip()

    if not author:
        raise ValueError("Please enter your name.")
    if not title:
        raise ValueError("Please enter a question title.")
    if not body:
        raise ValueError("Please enter your question.")

    created_at = timezone.localtime().isoformat()

    product = _product_model_by_id(product_id)
    if not product:
        raise ValueError("Product not found.")
    db_author = _get_or_create_author(
        author=author,
        author_username=author_username,
        author_user_id=author_user_id,
        identifier=f"question-{product_id}",
        prefix="questioner",
    )
    if not db_author:
        raise ValueError("Author not found.")
    db_question = ProductQuestionModel.objects.create(
        product=product,
        author=db_author,
        author_display_name_snapshot=author,
        title=title,
        body=body,
        is_visible=True,
    )
    return {
        "id": int(db_question.id),
        "product_id": product_id,
        "author": author,
        "author_username": str(db_author.username or author_username or ""),
        "author_user_id": int(db_author.id),
        "title": title,
        "body": body,
        "created_at": timezone.localtime(db_question.created_at).isoformat() if db_question.created_at else created_at,
        "answers": [],
    }


def create_answer(
    *,
    product_id: int,
    question_id: int,
    author: str,
    body: str,
    author_username: str | None = None,
    author_user_id: int | None = None,
) -> Dict[str, Any]:
    # 回答流程和提問一樣支援 ORM / JSON 兩種資料源，並回傳前端可直接 append 的資料。
    author = author.strip()
    body = body.strip()

    if not author:
        raise ValueError("Please enter your name.")
    if not body:
        raise ValueError("Please enter your answer.")

    created_at = timezone.localtime().isoformat()

    db_question = (
        ProductQuestionModel.objects.filter(id=question_id, product_id=product_id, is_visible=True)
        .select_related("author", "product")
        .first()
    )
    if not db_question:
        raise ValueError("Question not found.")
    db_author = _get_or_create_author(
        author=author,
        author_username=author_username,
        author_user_id=author_user_id,
        identifier=f"answer-{question_id}",
        prefix="responder",
    )
    if not db_author:
        raise ValueError("Author not found.")
    db_answer = ProductQuestionAnswerModel.objects.create(
        question=db_question,
        author=db_author,
        author_display_name_snapshot=author,
        body=body,
        is_visible=True,
    )
    return {
        "id": int(db_answer.id),
        "author": author,
        "author_username": str(db_author.username or author_username or ""),
        "author_user_id": int(db_author.id),
        "body": body,
        "created_at": timezone.localtime(db_answer.created_at).isoformat() if db_answer.created_at else created_at,
    }


def delete_question(question_id: int) -> None:
    # 刪除問題時一併刪掉其回答由底層資料源處理，這裡只負責一致的錯誤語意。
    found = False
    deleted, _ = ProductQuestionModel.objects.filter(id=question_id).delete()
    found = bool(deleted)

    if not found:
        raise ValueError("Question not found.")
