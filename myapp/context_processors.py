"""
全站共用的 context processor。

這個模組負責把導覽列、頁首或多個模板都會用到的資料，
集中注入到 Django template context，避免每個 view 重複準備同一批欄位。
"""
from __future__ import annotations

from .services import auth_demo
from .services import cart as cart_service
from .services import personalization as personalization_service


def cart_summary(request):
    """
    提供全站常用的購物車與登入狀態摘要。

    目前主要提供：
    - `cart_count`：購物車總件數
    - `cart_coupon`：目前已套用的折扣碼
    - `current_user`：目前登入中的示範會員快照
    - `compare_count`：商品比較清單數量

    Args:
        request: Django `HttpRequest`，用來讀取 session。

    Returns:
        dict: 會被注入所有模板的共用 context。
    """
    cart = cart_service.get_cart(request.session)
    return {
        "cart_count": cart_service.count_items(request.session),
        "cart_coupon": cart.get("coupon"),
        "current_user": auth_demo.get_current_user(request.session),
        "compare_count": len(personalization_service.get_compare_slugs(request.session)),
    }
