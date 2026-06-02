"""會員中心 / 個人首頁資料組裝 service。

來源模組：
- `myapp.repositories.local_store`
- `myapp.services.orders`
- `myapp.services.personalization`
- `myapp.services.product_management`

用途：
- 整理會員中心首頁需要的各種資料
- 將評論、問答、回答、文章、商品、訂單、收藏、最近瀏覽整合成單一 payload
- 供 `myapp.api.views.MeDashboardApi` 使用
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
    """把 ISO datetime 字串轉成前端較好閱讀的本地時間格式。

    來源模組：
    - `django.utils.dateparse.parse_datetime`
    - `django.utils.timezone.localtime`

    用途：
    - 會員中心列表頁只需要簡短時間字串
    - 避免前端每個區塊都各自做時間格式化
    """

    parsed = parse_datetime(value) if value else None
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M") if parsed else ""


def _matches_user(item: Dict[str, Any], username: str, display_name: str) -> bool:
    """判斷一筆內容是否屬於目前會員。

    用途：
    - 評論、問題、回答、社群文章目前都可能同時保存 `author_username` 或 `author`
    - 這裡統一比對 username 與 display_name，避免不同資料來源格式不一致
    """

    return item.get("author_username") == username or item.get("author") == display_name


def _product_stub(product_id: int) -> Dict[str, Any] | None:
    """用商品 id 取回精簡商品資訊。

    用途：
    - 評論 / 問答 / 回答清單只需要最小商品資訊
    - 避免把完整商品 payload 都塞進會員中心列表
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
    """列出會員撰寫過的商品評論。

    前端使用頁面：
    - 會員中心首頁
    - 未來若有「我的評論」頁也可重用

    功能：
    - 從 reviews JSON 篩出目前會員的評論
    - 補上商品 stub 與格式化時間
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
    """列出會員提出過的商品問題。

    前端使用頁面：
    - 會員中心首頁

    功能：
    - 從 questions JSON 篩出目前會員提問
    - 補上商品 stub、格式化時間與回答數量
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
    """列出會員回答過的商品問答。

    前端使用頁面：
    - 會員中心首頁

    功能：
    - 逐題展開 question answers
    - 找出目前會員留下的回答
    - 補上問題標題、商品 stub 與格式化時間
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
    """列出會員建立過的社群文章。

    前端使用頁面：
    - 會員中心首頁

    功能：
    - 從 posts JSON 篩出目前會員的貼文
    - 補上格式化時間與回覆數量
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
    """列出會員名下商品。

    前端使用頁面：
    - 會員中心首頁的賣家摘要
    - 後續若有「我建立的商品」摘要也可重用

    功能：
    - 讀取賣家自己的商品
    - 補上 created / updated 顯示時間
    """

    items = []
    for product in product_management.list_products_for_user(username):
        item = dict(product)
        item["created_at_display"] = _format_created_at(item.get("created_at", ""))
        item["updated_at_display"] = _format_created_at(item.get("updated_at", ""))
        items.append(item)
    return items


def build_profile_dashboard(user: Dict[str, str], session) -> Dict[str, Any]:
    """組裝會員中心首頁需要的完整 dashboard payload。

    前端使用頁面：
    - `frontend/app/me/page.tsx` 或對應會員中心首頁

    功能：
    - 聚合會員自己的內容資料
    - 聚合訂單、收藏、最近瀏覽
    - 回傳給 `MeDashboardApi` 一次輸出
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
