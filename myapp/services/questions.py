"""商品問答服務模組。

負責商品頁的提問、回答與問答摘要統計。
"""
from __future__ import annotations

from typing import Any, Dict, List

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..repositories import local_store


def _format_created_at(value: str) -> str:
    """格式化 商品問答 流程中使用的時間或顯示值。

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


def list_questions(product_id: int) -> List[Dict[str, Any]]:
    """列出 商品問答 相關資料，供頁面或 API 顯示。

    參數:
        product_id: 商品整數編號。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    questions = []
    for question in local_store.get_questions_by_product_id(product_id):
        item = dict(question)
        item["created_at_display"] = _format_created_at(item.get("created_at", ""))
        item["author_user_id"] = _resolve_author_user_id(item.get("author_user_id"), item.get("author_username"))

        answers = []
        for answer in item.get("answers", []):
            answer_item = dict(answer)
            answer_item["created_at_display"] = _format_created_at(answer_item.get("created_at", ""))
            answer_item["author_user_id"] = _resolve_author_user_id(answer_item.get("author_user_id"), answer_item.get("author_username"))
            answers.append(answer_item)
        item["answers"] = answers
        item["answer_count"] = len(answers)
        questions.append(item)
    return questions


def summarize_questions(product_id: int) -> Dict[str, int]:
    """處理 商品問答 相關流程。

    參數:
        product_id: 商品整數編號。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
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
    """建立新的商品問答主題。

    參數:
        product_id: 商品整數編號。
        author: 函式執行所需的輸入資料。
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
        raise ValueError("Please enter your name.")
    if not title:
        raise ValueError("Please enter a question title.")
    if not body:
        raise ValueError("Please enter your question.")

    questions = local_store.get_questions()
    next_id = max((question["id"] for question in questions), default=0) + 1
    question = {
        "id": next_id,
        "product_id": product_id,
        "author": author,
        "author_username": author_username,
        "author_user_id": author_user_id,
        "title": title,
        "body": body,
        "created_at": timezone.localtime().isoformat(),
        "answers": [],
    }
    questions.append(question)
    local_store.save_questions(questions)
    return question


def create_answer(
    *,
    product_id: int,
    question_id: int,
    author: str,
    body: str,
    author_username: str | None = None,
    author_user_id: int | None = None,
) -> Dict[str, Any]:
    """對指定商品問答新增回答內容。

    參數:
        product_id: 商品整數編號。
        question_id: 問答主題編號。
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
        raise ValueError("Please enter your answer.")

    questions = local_store.get_questions()
    for question in questions:
        if question.get("id") != question_id or question.get("product_id") != product_id:
            continue

        answers = question.setdefault("answers", [])
        next_id = max((answer["id"] for answer in answers), default=0) + 1
        answer = {
            "id": next_id,
            "author": author,
            "author_username": author_username,
            "author_user_id": author_user_id,
            "body": body,
            "created_at": timezone.localtime().isoformat(),
        }
        answers.append(answer)
        local_store.save_questions(questions)
        return answer

    raise ValueError("Question not found.")
