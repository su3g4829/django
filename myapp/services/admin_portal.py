"""平台後台首頁的資料聚合服務。

這個模組專門整理管理後台儀表板需要的摘要資料，
例如會員數、商品數、訂單摘要，以及最近的評論 / 問答 / 論壇文章。
"""
from __future__ import annotations

from typing import Any, Dict

from ..repositories import local_store
from . import auth_demo
from . import orders
from . import product_management


def build_dashboard() -> Dict[str, Any]:
    """建立平台管理後台首頁需要的摘要資料。

    回傳內容包含：
    - 會員總數、啟用數、停權數、賣家數、待審賣家申請數
    - 商品總數、上架數、待審商品數
    - 訂單摘要資料
    - 內容區塊統計（評論、問答、論壇文章）
    - 最新評論、最新問答、最新論壇文章

    Returns:
        dict: 提供給管理後台頁面或 API 使用的儀表板資料。
    """
    users = auth_demo.list_users()
    products = local_store.get_products()
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
            "active": len(product_management.list_public_products()),
            "pending": len(product_management.list_pending_products()),
        },
        "orders": orders.build_admin_order_summary(),
        "content": {
            "reviews": len(local_store.get_reviews()),
            "questions": len(local_store.get_questions()),
            "posts": len(local_store.get_posts()),
        },
        "recent_reviews": sorted(local_store.get_reviews(), key=lambda item: item.get("created_at", ""), reverse=True)[:5],
        "recent_questions": sorted(local_store.get_questions(), key=lambda item: item.get("created_at", ""), reverse=True)[:5],
        "recent_posts": sorted(local_store.get_posts(), key=lambda item: item.get("created_at", ""), reverse=True)[:5],
    }
